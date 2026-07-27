from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.models import (
    CrawlerAgent,
    CrawlerImageVersion,
    CrawlerProject,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskRun,
    CrawlerTaskRuntime,
    CrawlerTaskSchedule,
    CrawlerTaskTarget,
    SysSecret,
)
from app.security import decrypt_secret
from app.services.log_service import build_log_path
from app.utils import token_urlsafe, utcnow

ACTIVE_RUN_STATUSES = {"CLAIMED", "STARTING", "RUNNING"}
TERMINAL_RUN_STATUSES = {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED", "LOST", "SKIPPED"}


class RunCreationError(RuntimeError):
    pass


def make_run_no() -> str:
    now = utcnow()
    return f"RUN{now:%Y%m%d%H%M%S%f}-{token_urlsafe(4).replace('-', '').replace('_', '')[:6]}"


def choose_server(db: Session, task_id: int) -> CrawlerServer:
    targets = db.scalars(
        select(CrawlerTaskTarget)
        .where(CrawlerTaskTarget.task_id == task_id, CrawlerTaskTarget.enabled.is_(True))
        .order_by(CrawlerTaskTarget.priority.asc(), CrawlerTaskTarget.target_id.asc())
    ).all()
    if not targets:
        raise RunCreationError("任务没有绑定执行服务器")
    server_ids = [target.server_id for target in targets]
    servers = db.scalars(select(CrawlerServer).where(CrawlerServer.server_id.in_(server_ids))).all()
    server_map = {item.server_id: item for item in servers}
    for target in targets:
        server = server_map.get(target.server_id)
        if server and server.status == "ONLINE":
            return server
    first = server_map.get(targets[0].server_id)
    if not first:
        raise RunCreationError("任务绑定的服务器不存在")
    return first


def resolve_image(db: Session, task: CrawlerTask, runtime: CrawlerTaskRuntime) -> tuple[CrawlerProject, CrawlerImageVersion]:
    project = db.get(CrawlerProject, task.project_id)
    if not project:
        raise RunCreationError("爬虫项目不存在")

    image: CrawlerImageVersion | None = None
    if runtime.image_policy == "PINNED":
        if not runtime.fixed_image_version_id:
            raise RunCreationError("固定镜像策略必须指定镜像版本")
        image = db.get(CrawlerImageVersion, runtime.fixed_image_version_id)
    elif runtime.image_policy == "RELEASE_CHANNEL":
        channel = db.scalar(
            select(CrawlerReleaseChannel).where(
                CrawlerReleaseChannel.project_id == task.project_id,
                CrawlerReleaseChannel.channel_name == runtime.release_channel,
            )
        )
        if channel:
            image = db.get(CrawlerImageVersion, channel.image_version_id)
    elif runtime.image_policy == "LATEST_SUCCESSFUL":
        image = db.scalar(
            select(CrawlerImageVersion)
            .where(CrawlerImageVersion.project_id == task.project_id, CrawlerImageVersion.build_status == "SUCCESS")
            .order_by(CrawlerImageVersion.built_at.desc(), CrawlerImageVersion.image_version_id.desc())
        )
    else:
        raise RunCreationError(f"未知镜像策略：{runtime.image_policy}")

    if not image or image.project_id != task.project_id or image.build_status != "SUCCESS":
        raise RunCreationError("没有找到可用的成功构建镜像")
    return project, image


def create_run(
    db: Session,
    task: CrawlerTask,
    trigger_type: str,
    scheduled_at=None,
    triggered_by: int | None = None,
    schedule: CrawlerTaskSchedule | None = None,
    attempt: int = 1,
    parent_run_id: int | None = None,
) -> CrawlerTaskRun:
    if task.status != "ENABLED":
        raise RunCreationError("任务已停用")
    runtime = task.runtime or db.scalar(select(CrawlerTaskRuntime).where(CrawlerTaskRuntime.task_id == task.task_id))
    schedule = schedule or task.schedule or db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == task.task_id))
    if not runtime:
        raise RunCreationError("任务缺少容器运行配置")
    server = choose_server(db, task.task_id)
    project, image = resolve_image(db, task, runtime)
    scheduled_at = scheduled_at or utcnow()

    active_runs = db.scalars(
        select(CrawlerTaskRun).where(
            CrawlerTaskRun.task_id == task.task_id,
            CrawlerTaskRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    ).all()
    overlap_policy = schedule.overlap_policy if schedule else "SKIP"
    max_concurrency = schedule.max_concurrency if schedule else 1

    status = "QUEUED"
    if len(active_runs) >= max_concurrency:
        if overlap_policy == "SKIP":
            status = "SKIPPED"
        elif overlap_policy == "REPLACE":
            for item in active_runs:
                item.desired_action = "STOP"
        elif overlap_policy in {"QUEUE", "ALLOW"}:
            pass
        else:
            raise RunCreationError(f"未知重叠策略：{overlap_policy}")

    run_no = make_run_no()
    log_path = build_log_path(task.task_id, run_no, scheduled_at.strftime("%Y-%m-%d"))
    run = CrawlerTaskRun(
        run_no=run_no,
        task_id=task.task_id,
        schedule_id=schedule.schedule_id if schedule else None,
        server_id=server.server_id,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        scheduled_at=scheduled_at,
        queued_at=utcnow() if status == "QUEUED" else None,
        started_at=utcnow() if status == "SKIPPED" else None,
        finished_at=utcnow() if status == "SKIPPED" else None,
        status=status,
        attempt=attempt,
        parent_run_id=parent_run_id,
        image_name=f"{project.registry.rstrip('/')}/{project.repository.lstrip('/')}",
        image_tag=image.image_tag,
        image_digest=image.image_digest,
        git_commit=image.git_commit,
        log_path=str(log_path),
        error_type="OVERLAP_SKIPPED" if status == "SKIPPED" else "",
        error_message="已有任务实例运行，按重叠策略跳过" if status == "SKIPPED" else "",
    )
    db.add(run)
    db.flush()
    return run


def _resolve_secrets(db: Session, secret_refs: dict[str, str]) -> dict[str, str]:
    if not secret_refs:
        return {}
    codes = set(secret_refs.values())
    rows = db.scalars(select(SysSecret).where(SysSecret.secret_code.in_(codes), SysSecret.enabled.is_(True))).all()
    values = {row.secret_code: decrypt_secret(row.encrypted_value) for row in rows}
    missing = sorted(codes - set(values))
    if missing:
        raise RunCreationError(f"缺少或停用了密钥：{', '.join(missing)}")
    return {env_name: values[secret_code] for env_name, secret_code in secret_refs.items()}


def build_claim_payload(db: Session, run: CrawlerTaskRun) -> dict[str, Any]:
    task = db.scalar(
        select(CrawlerTask)
        .options(selectinload(CrawlerTask.runtime), selectinload(CrawlerTask.schedule))
        .where(CrawlerTask.task_id == run.task_id)
    )
    if not task or not task.runtime:
        raise RunCreationError("任务配置不存在")
    runtime = task.runtime
    resolved_secrets = _resolve_secrets(db, runtime.secret_refs or {})
    image_ref = f"{run.image_name}@{run.image_digest}" if run.image_digest else f"{run.image_name}:{run.image_tag}"
    return {
        "run_id": run.run_id,
        "run_no": run.run_no,
        "task_id": task.task_id,
        "task_code": task.task_code,
        "task_name": task.task_name,
        "executor_type": task.executor_type,
        "entrypoint": task.entrypoint,
        "arguments": task.arguments or [],
        "keyword_arguments": task.keyword_arguments or {},
        "image_ref": image_ref,
        "image_name": run.image_name,
        "image_tag": run.image_tag,
        "image_digest": run.image_digest,
        "pull_policy": runtime.pull_policy,
        "container_command": runtime.container_command or [],
        "container_working_dir": runtime.container_working_dir,
        "environment_variables": runtime.environment_variables or {},
        "resolved_secrets": resolved_secrets,
        "volume_mounts": runtime.volume_mounts or [],
        "network_mode": runtime.network_mode,
        "cpu_limit": float(runtime.cpu_limit),
        "memory_limit_mb": runtime.memory_limit_mb,
        "shm_size_mb": runtime.shm_size_mb,
        "pids_limit": runtime.pids_limit,
        "stop_grace_seconds": runtime.stop_grace_seconds,
        "auto_remove": runtime.auto_remove,
        "keep_failed_container": runtime.keep_failed_container,
        "timeout_seconds": task.schedule.timeout_seconds if task.schedule else 3600,
    }


def claim_runs(db: Session, agent: CrawlerAgent, limit: int) -> list[dict[str, Any]]:
    now = utcnow()
    rows = db.scalars(
        select(CrawlerTaskRun)
        .where(CrawlerTaskRun.server_id == agent.server_id, CrawlerTaskRun.status == "QUEUED")
        .order_by(CrawlerTaskRun.queued_at.asc(), CrawlerTaskRun.run_id.asc())
        .with_for_update(skip_locked=True)
        .limit(limit * 4)
    ).all()
    claimed: list[dict[str, Any]] = []
    for run in rows:
        if len(claimed) >= limit:
            break
        schedule = db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == run.task_id))
        max_concurrency = schedule.max_concurrency if schedule else 1
        overlap_policy = schedule.overlap_policy if schedule else "SKIP"
        active_count = db.scalar(
            select(func.count(CrawlerTaskRun.run_id)).where(
                CrawlerTaskRun.task_id == run.task_id,
                CrawlerTaskRun.run_id != run.run_id,
                CrawlerTaskRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        ) or 0
        if overlap_policy != "ALLOW" and active_count >= max_concurrency:
            continue
        run.status = "CLAIMED"
        run.agent_id = agent.agent_id
        run.claimed_at = now
        run.heartbeat_at = now
        run.lease_expires_at = now + timedelta(seconds=settings.agent_lease_seconds)
        try:
            payload = build_claim_payload(db, run)
        except Exception as exc:
            run.status = "FAILED"
            run.finished_at = now
            run.error_type = "CONFIG_ERROR"
            run.error_message = str(exc)
            run.lease_expires_at = None
            continue
        claimed.append(payload)
    db.flush()
    return claimed


def task_query_with_relations():
    return select(CrawlerTask).options(
        selectinload(CrawlerTask.runtime),
        selectinload(CrawlerTask.schedule),
        selectinload(CrawlerTask.targets),
    )
