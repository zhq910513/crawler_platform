from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_agent
from app.models import (
    CrawlerAgent,
    CrawlerContainerEvent,
    CrawlerServer,
    CrawlerServerMetric,
    CrawlerTaskRun,
)
from app.schemas import (
    AgentHeartbeat,
    AgentRegisterRequest,
    AgentRegisterResponse,
    ClaimRequest,
    ContainerEventRequest,
    RunFinishRequest,
    RunHeartbeatRequest,
    RunLogAppendRequest,
    RunStartedRequest,
)
from app.services.log_service import append_lines
from app.services.run_service import claim_runs
from app.utils import sha256_text, token_urlsafe, utcnow

router = APIRouter(prefix="/agent", tags=["Agent"])


def _owned_run(db: Session, agent: CrawlerAgent, run_id: int) -> CrawlerTaskRun:
    row = db.get(CrawlerTaskRun, run_id)
    if not row or row.agent_id != agent.agent_id or row.server_id != agent.server_id:
        raise HTTPException(status_code=404, detail="运行实例不存在或不属于当前 Agent")
    return row


@router.post("/register", response_model=AgentRegisterResponse)
def register_agent(
    payload: AgentRegisterRequest,
    x_agent_bootstrap_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AgentRegisterResponse:
    if x_agent_bootstrap_token != settings.agent_bootstrap_token:
        raise HTTPException(status_code=401, detail="Agent Bootstrap Token 无效")
    server = db.scalar(select(CrawlerServer).where(CrawlerServer.server_code == payload.server_code))
    if not server:
        server = CrawlerServer(
            server_code=payload.server_code,
            server_name=payload.server_name,
            server_ip=payload.server_ip,
            environment=payload.environment,
            max_container_slots=payload.max_container_slots,
            status="ONLINE",
        )
        db.add(server)
        db.flush()
    else:
        server.server_name = payload.server_name
        server.server_ip = payload.server_ip
        server.environment = payload.environment
        server.max_container_slots = payload.max_container_slots
        server.status = "ONLINE"

    token = token_urlsafe(48)
    agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.server_id == server.server_id))
    if not agent:
        agent = CrawlerAgent(server_id=server.server_id, agent_code=payload.agent_code, token_hash=sha256_text(token))
        db.add(agent)
    agent.agent_code = payload.agent_code
    agent.token_hash = sha256_text(token)
    agent.agent_version = payload.agent_version
    agent.hostname = payload.hostname
    agent.os_name = payload.os_name
    agent.python_version = payload.python_version
    agent.docker_version = payload.docker_version
    agent.cpu_count = payload.cpu_count
    agent.memory_total_bytes = payload.memory_total_bytes
    agent.status = "ONLINE"
    agent.last_ip = payload.server_ip
    agent.started_at = utcnow()
    agent.last_heartbeat_at = utcnow()
    agent.last_error = ""
    db.commit()
    db.refresh(agent)
    return AgentRegisterResponse(agent_id=agent.agent_id, server_id=server.server_id, agent_token=token, lease_seconds=settings.agent_lease_seconds)


@router.post("/heartbeat")
def heartbeat(payload: AgentHeartbeat, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    now = utcnow()
    server = db.get(CrawlerServer, agent.server_id)
    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")
    agent.agent_version = payload.agent_version
    agent.hostname = payload.hostname
    agent.os_name = payload.os_name
    agent.python_version = payload.python_version
    agent.docker_version = payload.docker_version
    agent.cpu_count = payload.cpu_count
    agent.memory_total_bytes = payload.memory_total_bytes
    agent.status = "ONLINE"
    agent.last_ip = payload.server_ip
    agent.last_heartbeat_at = now
    agent.last_error = payload.last_error
    server.server_ip = payload.server_ip or server.server_ip
    if server.status != "DISABLED":
        server.status = "ONLINE"

    latest_metric = db.scalar(
        select(CrawlerServerMetric)
        .where(CrawlerServerMetric.server_id == server.server_id)
        .order_by(CrawlerServerMetric.metric_id.desc())
        .limit(1)
    )
    if not latest_metric or latest_metric.recorded_at <= now - timedelta(seconds=60):
        db.add(
            CrawlerServerMetric(
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
            )
        )
    db.commit()
    return {"ok": True, "server_status": server.status, "lease_seconds": settings.agent_lease_seconds}


@router.post("/claim")
def claim(payload: ClaimRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    server = db.get(CrawlerServer, agent.server_id)
    if not server or server.status == "DISABLED":
        return {"items": []}
    items = claim_runs(db, agent, payload.limit)
    db.commit()
    return {"items": items}


@router.post("/runs/{run_id}/started")
def run_started(run_id: int, payload: RunStartedRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    if row.status not in {"CLAIMED", "STARTING"}:
        raise HTTPException(status_code=409, detail=f"当前状态不允许启动：{row.status}")
    now = utcnow()
    row.status = "RUNNING"
    row.container_id = payload.container_id
    row.container_name = payload.container_name
    row.started_at = row.started_at or now
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
    db.commit()
    return {"ok": True}


@router.post("/runs/{run_id}/heartbeat")
def run_heartbeat(run_id: int, payload: RunHeartbeatRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    if row.status not in {"CLAIMED", "STARTING", "RUNNING"}:
        return {"ok": False, "desired_action": row.desired_action, "status": row.status}
    now = utcnow()
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
    if payload.container_id:
        row.container_id = payload.container_id
    db.commit()
    return {"ok": True, "desired_action": row.desired_action, "status": row.status}


@router.get("/runs/{run_id}/control")
def run_control(run_id: int, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    return {"desired_action": row.desired_action, "status": row.status}


@router.post("/runs/{run_id}/finish")
def run_finish(run_id: int, payload: RunFinishRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    now = utcnow()
    row.status = payload.status
    row.finished_at = now
    row.exit_code = payload.exit_code
    row.error_type = payload.error_type
    row.error_message = payload.error_message
    row.inspect_summary = payload.inspect_summary
    row.heartbeat_at = now
    row.lease_expires_at = None
    row.desired_action = "NONE"
    if row.started_at:
        row.duration_ms = int((now - row.started_at).total_seconds() * 1000)
    db.commit()
    return {"ok": True}


@router.post("/runs/{run_id}/logs")
async def run_logs(run_id: int, payload: RunLogAppendRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    size, line_count = await append_lines(run_id, Path(row.log_path), payload.lines)
    row.log_size_bytes = size
    row.last_log_at = utcnow()
    db.commit()
    return {"ok": True, "line_count": line_count, "log_size_bytes": size}


@router.post("/runs/{run_id}/events")
def container_event(run_id: int, payload: ContainerEventRequest, db: Session = Depends(get_db), agent: CrawlerAgent = Depends(get_agent)) -> dict:
    row = _owned_run(db, agent, run_id)
    db.add(
        CrawlerContainerEvent(
            run_id=row.run_id,
            server_id=row.server_id,
            container_id=payload.container_id,
            container_name=payload.container_name,
            event_type=payload.event_type,
            event_action=payload.event_action,
            exit_code=payload.exit_code,
            event_message=payload.event_message,
        )
    )
    db.commit()
    return {"ok": True}
