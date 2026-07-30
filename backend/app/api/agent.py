from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_agent
from app.models import (
    CrawlerAgent,
    CrawlerContainerEvent,
    CrawlerServer,
    CrawlerServerMetric,
    CrawlerSpiderEntry,
    CrawlerTask,
    CrawlerTaskRun,
    CrawlerTaskRuntime,
    CrawlerTaskRunEvent,
)
from app.schemas import (
    AgentHeartbeat,
    AgentRegisterRequest,
    AgentRegisterResponse,
    ClaimRequest,
    ContainerEventRequest,
    LogBatchRequest,
    RunEventBatchRequest,
    RunFinishRequest,
    RunHeartbeatRequest,
    RunStartedRequest,
    RunStartingRequest,
)
from app.services.log_service import append_lines
from app.services.resource_manifest import ResourceManifestError, resolve_manifest_secrets
from app.services.run_state import ACTIVE_STATUSES, TERMINAL_STATUSES, InvalidRunTransition, transition
from app.utils import sha256_text, token_urlsafe, utcnow

router = APIRouter(prefix="/agent/v2", tags=["Agent V2"])

SENSITIVE_KEYS = {"password", "passwd", "pwd", "secret", "token", "cookie", "authorization", "access_key", "private_key", "uri"}


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("***REDACTED***" if any(x in str(k).lower() for x in SENSITIVE_KEYS) else _sanitize(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _owned_run(
    db: Session,
    agent: CrawlerAgent,
    run_id: int,
    lease_token: str | None,
    *,
    allow_terminal: bool = True,
) -> CrawlerTaskRun:
    row = db.get(CrawlerTaskRun, run_id)
    if not row or row.agent_id != agent.agent_id or row.server_id != agent.server_id:
        raise HTTPException(status_code=404, detail="运行实例不存在或不属于当前 Agent")
    if not lease_token or not row.lease_token or not hmac.compare_digest(lease_token, row.lease_token):
        raise HTTPException(status_code=409, detail="运行租约令牌无效")
    if not allow_terminal and row.status in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail=f"运行已结束：{row.status}")
    return row


def _run_runtime(db: Session, run: CrawlerTaskRun) -> CrawlerTaskRuntime:
    runtime = db.scalar(select(CrawlerTaskRuntime).where(CrawlerTaskRuntime.task_id == run.task_id))
    if not runtime:
        raise HTTPException(status_code=409, detail="任务运行配置不存在")
    return runtime


def _claim_item(db: Session, run: CrawlerTaskRun) -> dict[str, Any]:
    entry = db.get(CrawlerSpiderEntry, run.spider_entry_id)
    if not entry or not run.resource_manifest_json or not run.task_spec_json:
        raise HTTPException(status_code=409, detail=f"运行 {run.run_id} 缺少 V2 执行合同")
    try:
        secrets = resolve_manifest_secrets(db, int(run.project_id), run.resource_manifest_json)
    except ResourceManifestError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    runtime = dict(run.runtime_json or {})
    if not runtime:
        legacy = _run_runtime(db, run)
        runtime = {
            "pull_policy": legacy.pull_policy,
            "cpu_limit": float(legacy.cpu_limit),
            "memory_limit_mb": legacy.memory_limit_mb,
            "shm_size_mb": legacy.shm_size_mb,
            "pids_limit": legacy.pids_limit,
            "stop_grace_seconds": legacy.stop_grace_seconds,
            "auto_remove": legacy.auto_remove,
            "keep_failed_container": legacy.keep_failed_container,
        }
    return {
        "protocol_version": "2.0",
        "run_id": run.run_id,
        "run_no": run.run_no,
        "task_id": run.task_id,
        "lease_token": run.lease_token,
        "image": {
            "ref": f"{run.image_name}@{run.image_digest}",
            "repository": run.image_name,
            "digest": run.image_digest,
            "profile": entry.image_profile,
            "pull_policy": runtime.get("pull_policy", "IF_NOT_PRESENT"),
        },
        "files": {
            "task": run.task_spec_json,
            "resources": run.resource_manifest_json,
            "secrets": secrets,
        },
        "runtime": {
            "cpu_limit": float(runtime.get("cpu_limit", 2)),
            "memory_limit_mb": int(runtime.get("memory_limit_mb", 4096)),
            "shm_size_mb": int(runtime.get("shm_size_mb", 256)),
            "pids_limit": int(runtime.get("pids_limit", 512)),
            "stop_grace_seconds": int(runtime.get("stop_grace_seconds", 30)),
            "timeout_seconds": int((run.task_spec_json or {}).get("timeout_seconds", 3600)),
            "auto_remove": bool(runtime.get("auto_remove", True)),
            "keep_failed_container": bool(runtime.get("keep_failed_container", False)),
        },
    }


@router.post("/register", response_model=AgentRegisterResponse)
def register_agent(
    payload: AgentRegisterRequest,
    request: Request,
    x_agent_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentRegisterResponse:
    if not x_agent_bootstrap_token or not hmac.compare_digest(x_agent_bootstrap_token, settings.agent_bootstrap_token):
        raise HTTPException(status_code=401, detail="Agent Bootstrap Token 无效")
    server = db.scalar(select(CrawlerServer).where(CrawlerServer.server_code == payload.server_code))
    if server and server.status == "DISABLED":
        raise HTTPException(status_code=403, detail="该 Agent 服务器已被平台禁用")
    code_owner = db.scalar(select(CrawlerAgent).where(CrawlerAgent.agent_code == payload.agent_code))
    if code_owner and server and code_owner.server_id != server.server_id:
        raise HTTPException(status_code=409, detail="Agent 编码已被其他服务器使用")
    if code_owner and not server:
        raise HTTPException(status_code=409, detail="Agent 编码已存在，但 SERVER_CODE 不匹配")
    client_ip = request.client.host if request.client else ""
    if not server:
        server = CrawlerServer(
            server_code=payload.server_code,
            server_name=payload.server_name,
            server_ip=client_ip,
            max_container_slots=payload.max_container_slots,
            status="ONLINE",
        )
        db.add(server)
        db.flush()
    else:
        server.server_name = payload.server_name
        server.server_ip = client_ip or server.server_ip
        server.max_container_slots = payload.max_container_slots
        if server.status != "DISABLED":
            server.status = "ONLINE"
    token = token_urlsafe(48)
    agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.server_id == server.server_id))
    if not agent:
        agent = CrawlerAgent(server_id=server.server_id, agent_code=payload.agent_code, token_hash=sha256_text(token))
        db.add(agent)
    agent.agent_code = payload.agent_code
    agent.token_hash = sha256_text(token)
    agent.protocol_version = payload.protocol_version
    agent.instance_id = payload.instance_id
    agent.agent_version = payload.agent_version
    agent.hostname = payload.hostname
    agent.os_name = payload.os_name
    agent.python_version = payload.python_version
    agent.docker_version = payload.docker_version
    agent.cpu_count = payload.cpu_count
    agent.memory_total_bytes = payload.memory_total_bytes
    agent.capabilities_json = payload.capabilities
    agent.labels_json = payload.labels
    agent.status = "ONLINE"
    agent.last_ip = client_ip
    agent.started_at = utcnow()
    agent.last_heartbeat_at = utcnow()
    agent.last_error = ""
    db.commit()
    db.refresh(agent)
    return AgentRegisterResponse(
        agent_id=agent.agent_id,
        server_id=server.server_id,
        agent_token=token,
        lease_seconds=settings.agent_lease_seconds,
    )


@router.post("/heartbeat")
def heartbeat(payload: AgentHeartbeat, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    if payload.instance_id != agent.instance_id:
        raise HTTPException(status_code=409, detail="Agent 实例已被新的进程替代，请重新注册")
    now = utcnow()
    server = db.get(CrawlerServer, agent.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    agent.status = payload.status
    agent.last_heartbeat_at = now
    agent.last_error = payload.last_error
    if server.status != "DISABLED":
        server.status = "ONLINE" if payload.status == "ONLINE" else "DEGRADED"
    latest = db.scalar(
        select(CrawlerServerMetric)
        .where(CrawlerServerMetric.server_id == server.server_id)
        .order_by(CrawlerServerMetric.metric_id.desc()).limit(1)
    )
    if not latest or latest.recorded_at <= now - timedelta(seconds=30):
        db.add(CrawlerServerMetric(
            server_id=server.server_id,
            cpu_percent=payload.cpu_percent,
            memory_percent=payload.memory_percent,
            disk_percent=payload.disk_percent,
            load_1m=payload.load_1m,
            load_5m=payload.load_5m,
            network_sent_bytes=payload.network_sent_bytes,
            network_received_bytes=payload.network_received_bytes,
            running_task_count=payload.running_task_count,
            process_count=payload.process_count,
            docker_image_bytes=payload.docker_image_bytes,
            recorded_at=now,
        ))
    db.commit()
    return {"ok": True, "lease_seconds": settings.agent_lease_seconds, "server_status": server.status}


@router.post("/claim")
def claim(payload: ClaimRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    server = db.get(CrawlerServer, agent.server_id)
    if not server or server.status == "DISABLED" or payload.available_slots <= 0:
        return {"items": []}
    active = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(
        CrawlerTaskRun.agent_id == agent.agent_id,
        CrawlerTaskRun.status.in_(ACTIVE_STATUSES),
    )) or 0
    limit = min(payload.available_slots, max(0, server.max_container_slots - active), 20)
    if limit <= 0:
        return {"items": []}
    rows = db.scalars(
        select(CrawlerTaskRun)
        .where(CrawlerTaskRun.server_id == server.server_id, CrawlerTaskRun.status == "QUEUED")
        .order_by(CrawlerTaskRun.scheduled_at.asc(), CrawlerTaskRun.run_id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit)
    ).all()
    now = utcnow()
    items: list[dict[str, Any]] = []
    for run in rows:
        run.agent_id = agent.agent_id
        run.lease_token = token_urlsafe(48)
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
        transition(run, "ASSIGNED")
        items.append(_claim_item(db, run))
    db.commit()
    return {"items": items}


@router.post("/runs/{run_id}/starting")
def run_starting(
    run_id: int,
    payload: RunStartingRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token, allow_terminal=False)
    try:
        transition(run, "STARTING")
    except InvalidRunTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run.heartbeat_at = utcnow()
    run.lease_expires_at = utcnow() + timedelta(seconds=settings.agent_lease_seconds)
    db.commit()
    return {"ok": True, "status": run.status}


@router.post("/runs/{run_id}/started")
def run_started(
    run_id: int,
    payload: RunStartedRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token, allow_terminal=False)
    try:
        transition(run, "RUNNING")
    except InvalidRunTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    run.container_id = payload.container_id
    run.container_name = payload.container_name
    run.heartbeat_at = utcnow()
    run.lease_expires_at = utcnow() + timedelta(seconds=settings.agent_lease_seconds)
    db.commit()
    return {"ok": True, "status": run.status}


@router.post("/runs/{run_id}/heartbeat")
def run_heartbeat(
    run_id: int,
    payload: RunHeartbeatRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    if run.status in TERMINAL_STATUSES:
        return {"ok": False, "status": run.status, "desired_action": "STOP"}
    run.heartbeat_at = utcnow()
    run.lease_expires_at = utcnow() + timedelta(seconds=settings.agent_lease_seconds)
    if payload.container_id:
        run.container_id = payload.container_id
    db.commit()
    return {"ok": True, "status": run.status, "desired_action": run.desired_action}


@router.get("/runs/{run_id}/control")
def run_control(
    run_id: int,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    return {"status": run.status, "desired_action": run.desired_action}


@router.post("/runs/{run_id}/logs")
async def run_logs(
    run_id: int,
    payload: LogBatchRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    ack_field = "stdout_ack_seq" if payload.stream == "stdout" else "stderr_ack_seq"
    ack_seq = int(getattr(run, ack_field) or 0)
    if payload.start_seq > ack_seq + 1:
        raise HTTPException(status_code=409, detail={"code": "AGENT.LOG_SEQUENCE_GAP", "ack_seq": ack_seq})
    skip = max(0, ack_seq - payload.start_seq + 1)
    accepted = payload.lines[skip:]
    if accepted:
        size, _ = await append_lines(run_id, Path(run.log_path), accepted)
        ack_seq += len(accepted)
        setattr(run, ack_field, ack_seq)
        run.log_size_bytes = size
        run.last_log_at = utcnow()
        db.commit()
    return {"stream": payload.stream, "ack_seq": ack_seq, "accepted_count": len(accepted)}


@router.post("/runs/{run_id}/events")
def run_events(
    run_id: int,
    payload: RunEventBatchRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    accepted = 0
    max_event_id = 0
    for item in payload.events:
        existing = db.scalar(select(CrawlerTaskRunEvent).where(
            CrawlerTaskRunEvent.run_id == run_id,
            CrawlerTaskRunEvent.event_uid == item.event_uid,
        ))
        if existing:
            max_event_id = max(max_event_id, existing.event_id)
            continue
        event = CrawlerTaskRunEvent(
            run_id=run_id,
            event_uid=item.event_uid,
            stream=item.stream,
            seq=item.seq,
            level=item.level.upper(),
            event_name=item.event_name,
            message=item.message,
            error_code=item.error_code,
            error_type=item.error_type,
            retryable=item.retryable,
            context_json=_sanitize(item.context),
            payload_json=_sanitize(item.payload),
            occurred_at=item.occurred_at or utcnow(),
        )
        db.add(event)
        db.flush()
        accepted += 1
        max_event_id = max(max_event_id, event.event_id)
        if event.level in {"ERROR", "CRITICAL"}:
            run.last_error_event_id = event.event_uid
            run.last_error_code = event.error_code or "SPIDER.ERROR"
            run.last_error_type = event.error_type or "CrawlerError"
            run.last_error_message = event.message
            run.last_error_at = event.occurred_at
            run.last_error_log_seq = event.seq
    db.commit()
    return {"accepted_count": accepted, "ack_event_id": max_event_id}


@router.post("/runs/{run_id}/container-events")
def container_event(
    run_id: int,
    payload: ContainerEventRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    db.add(CrawlerContainerEvent(
        run_id=run.run_id,
        server_id=run.server_id,
        container_id=payload.container_id,
        container_name=payload.container_name,
        event_type=payload.event_type,
        event_action=payload.event_action,
        exit_code=payload.exit_code,
        event_message=payload.event_message,
    ))
    db.commit()
    return {"ok": True}


@router.post("/runs/{run_id}/finish")
def run_finish(
    run_id: int,
    payload: RunFinishRequest,
    x_run_lease_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    agent: CrawlerAgent = Depends(get_agent),
) -> dict:
    run = _owned_run(db, agent, run_id, x_run_lease_token)
    if run.status not in TERMINAL_STATUSES:
        try:
            transition(run, payload.status)
        except InvalidRunTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    run.exit_code = payload.exit_code
    run.oom_killed = payload.oom_killed
    run.inspect_summary = _sanitize(payload.inspect_summary)
    run.result_json = _sanitize(payload.result)
    if isinstance(payload.result, dict):
        run.metrics_json = _sanitize(payload.result.get("metrics") or {})
    last_error = payload.last_error or {}
    if last_error and not run.last_error_message:
        run.last_error_code = str(last_error.get("code", "SPIDER.ERROR"))[:200]
        run.last_error_type = str(last_error.get("type", "CrawlerError"))[:200]
        run.last_error_message = str(last_error.get("message", ""))
        run.last_error_at = utcnow()
    terminal = payload.terminal_error or {}
    if terminal:
        run.terminal_error_code = str(terminal.get("code", "SPIDER.FAILED"))[:200]
        run.terminal_error_type = str(terminal.get("type", "CrawlerError"))[:200]
        run.terminal_error_message = str(terminal.get("message", ""))
        run.terminal_error_retryable = bool(terminal.get("retryable", False))
        run.terminal_error_json = _sanitize(terminal)
        run.error_type = run.terminal_error_type
        run.error_message = run.terminal_error_message
    elif payload.status in {"FAILED", "TIMED_OUT"}:
        run.terminal_error_code = "AGENT.CONTAINER_FAILURE" if payload.status == "FAILED" else "AGENT.TASK_TIMEOUT"
        run.terminal_error_type = "ContainerError" if payload.status == "FAILED" else "TaskTimeoutError"
        run.terminal_error_message = run.last_error_message or ("任务执行超时" if payload.status == "TIMED_OUT" else "容器执行失败")
        run.error_type = run.terminal_error_type
        run.error_message = run.terminal_error_message
    run.heartbeat_at = utcnow()
    run.lease_expires_at = None
    run.desired_action = "NONE"
    db.commit()
    return {"ok": True, "status": run.status}
