from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    CrawlerAgent,
    CrawlerProject,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerSpiderEntry,
    CrawlerSpiderRelease,
    CrawlerTask,
    CrawlerTaskRun,
    CrawlerTaskRuntime,
    CrawlerTaskSchedule,
    CrawlerTaskTarget,
)
from app.services.log_service import build_log_path
from app.services.resource_manifest import ResourceManifestError, build_resource_files
from app.utils import token_urlsafe, utcnow

ACTIVE_RUN_STATUSES = {"ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
TERMINAL_RUN_STATUSES = {"SUCCEEDED", "PARTIAL_SUCCESS", "SKIPPED", "FAILED", "CANCELLED", "TIMED_OUT", "LOST"}


class RunCreationError(RuntimeError):
    pass


def make_run_no() -> str:
    now = utcnow()
    suffix = token_urlsafe(4).replace("-", "").replace("_", "")[:6]
    return f"RUN{now:%Y%m%d%H%M%S%f}-{suffix}"


def choose_server(db: Session, task_id: int, required_capability: str) -> CrawlerServer:
    targets = db.scalars(
        select(CrawlerTaskTarget)
        .where(CrawlerTaskTarget.task_id == task_id, CrawlerTaskTarget.enabled.is_(True))
        .order_by(CrawlerTaskTarget.priority.asc(), CrawlerTaskTarget.target_id.asc())
    ).all()
    if not targets:
        raise RunCreationError("任务没有绑定 Agent 服务器")

    candidates: list[tuple[tuple[int, float, int, int], CrawlerServer]] = []
    for target in targets:
        server = db.get(CrawlerServer, target.server_id)
        if not server or server.status not in {"ONLINE", "DEGRADED"}:
            continue
        agent = db.scalar(select(CrawlerAgent).where(CrawlerAgent.server_id == server.server_id))
        if not agent or agent.status not in {"ONLINE", "DEGRADED"}:
            continue
        capabilities = set(agent.capabilities_json or [])
        if required_capability not in capabilities:
            continue
        active = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(
            CrawlerTaskRun.server_id == server.server_id,
            CrawlerTaskRun.status.in_(ACTIVE_RUN_STATUSES),
        )) or 0
        capacity = max(1, server.max_container_slots)
        score = (1 if active >= capacity else 0, active / capacity, target.priority, target.target_id)
        candidates.append((score, server))
    if not candidates:
        raise RunCreationError(f"任务绑定的 Agent 均不可用或不支持 {required_capability} 运行能力")
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def resolve_release(
    db: Session, task: CrawlerTask, runtime: CrawlerTaskRuntime
) -> tuple[CrawlerSpiderRelease, CrawlerSpiderEntry]:
    release: CrawlerSpiderRelease | None = None
    if runtime.image_policy == "PINNED":
        if not runtime.fixed_spider_release_id:
            raise RunCreationError("固定发布策略未指定 SpiderRelease")
        release = db.get(CrawlerSpiderRelease, runtime.fixed_spider_release_id)
    elif runtime.image_policy == "RELEASE_CHANNEL":
        channel = db.scalar(
            select(CrawlerReleaseChannel).where(
                CrawlerReleaseChannel.project_id == task.project_id,
                CrawlerReleaseChannel.channel_name == runtime.release_channel,
            )
        )
        if channel and channel.spider_release_id:
            release = db.get(CrawlerSpiderRelease, channel.spider_release_id)
    else:
        raise RunCreationError(f"不支持的发布策略：{runtime.image_policy}")
    if not release or release.status != "ACTIVE":
        raise RunCreationError("没有找到可用的 crawler_platform_spiders 发布版本")
    entry = db.scalar(
        select(CrawlerSpiderEntry).where(
            CrawlerSpiderEntry.release_id == release.release_id,
            CrawlerSpiderEntry.task_name == task.spider_task_name,
        )
    )
    if not entry:
        raise RunCreationError(f"发布版本中不存在入口：{task.spider_task_name}")
    return release, entry


def runtime_snapshot(runtime: CrawlerTaskRuntime) -> dict[str, Any]:
    return {
        "pull_policy": runtime.pull_policy,
        "cpu_limit": float(runtime.cpu_limit),
        "memory_limit_mb": runtime.memory_limit_mb,
        "shm_size_mb": runtime.shm_size_mb,
        "pids_limit": runtime.pids_limit,
        "stop_grace_seconds": runtime.stop_grace_seconds,
        "auto_remove": runtime.auto_remove,
        "keep_failed_container": runtime.keep_failed_container,
    }


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
    project = db.get(CrawlerProject, task.project_id)
    if not project or not project.company_id:
        raise RunCreationError("任务项目不存在或未绑定公司")
    runtime = task.runtime or db.scalar(select(CrawlerTaskRuntime).where(CrawlerTaskRuntime.task_id == task.task_id))
    schedule = schedule or task.schedule or db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == task.task_id))
    if not runtime:
        raise RunCreationError("任务缺少运行配置")
    if schedule:
        active_count = db.scalar(
            select(func.count(CrawlerTaskRun.run_id)).where(
                CrawlerTaskRun.task_id == task.task_id,
                CrawlerTaskRun.status.in_(ACTIVE_RUN_STATUSES),
            )
        ) or 0
        if active_count >= schedule.max_concurrency and schedule.overlap_policy == "SKIP":
            raise RunCreationError("任务已达到最大并发，按重叠策略跳过")
    release, entry = resolve_release(db, task, runtime)
    server = choose_server(db, task.task_id, entry.image_profile)
    timeout_seconds = schedule.timeout_seconds if schedule else entry.default_timeout_seconds
    max_attempts = (schedule.max_retry_count + 1) if schedule else 1
    try:
        resource_manifest, _ = build_resource_files(
            db,
            company_id=project.company_id,
            project_id=project.project_id,
            required_resources=list(entry.required_resources or []),
        )
    except ResourceManifestError as exc:
        raise RunCreationError(str(exc)) from exc
    now = utcnow()
    created_at = now.isoformat().replace("+00:00", "Z") if now.tzinfo else now.isoformat() + "Z"
    trigger_name = {
        "SCHEDULE": "schedule", "MANUAL": "manual", "RETRY": "retry", "API": "api"
    }.get(trigger_type, "system")
    run_no = make_run_no()
    task_spec = {
        "schema_version": "1.0",
        "project_name": "crawler_platform_spiders",
        "company_id": str(project.company_id),
        "project_id": str(project.project_id),
        "task_id": str(task.task_id),
        "run_id": "pending",
        "task_name": entry.task_name,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "timeout_seconds": timeout_seconds,
        "triggered_by": trigger_name,
        "triggered_by_user_id": str(triggered_by) if triggered_by else None,
        "created_at": created_at,
        "parameters": task.parameters or {},
    }
    root_run_id = None
    if parent_run_id:
        parent = db.get(CrawlerTaskRun, parent_run_id)
        root_run_id = (parent.root_run_id or parent.run_id) if parent else parent_run_id
    run = CrawlerTaskRun(
        run_no=run_no,
        company_id=project.company_id,
        project_id=project.project_id,
        task_id=task.task_id,
        schedule_id=schedule.schedule_id if schedule else None,
        server_id=server.server_id,
        spider_release_id=release.release_id,
        spider_entry_id=entry.entry_id,
        trigger_type=trigger_type,
        triggered_by=triggered_by,
        scheduled_at=scheduled_at or now,
        queued_at=now,
        status="QUEUED",
        attempt=attempt,
        max_attempts=max_attempts,
        parent_run_id=parent_run_id,
        root_run_id=root_run_id,
        image_name=release.image_repository,
        image_tag=release.image_tag,
        image_digest=release.image_digest,
        git_commit=release.git_commit,
        task_spec_json=task_spec,
        resource_manifest_json=resource_manifest,
        runtime_json=runtime_snapshot(runtime),
        log_path="",
    )
    db.add(run)
    db.flush()
    run.root_run_id = run.root_run_id or run.run_id
    run.task_spec_json = {**task_spec, "run_id": str(run.run_id)}
    run.log_path = str(build_log_path(task.task_id, run.run_no, now.date().isoformat()))
    db.flush()
    return run


def create_retry(
    db: Session,
    failed_run: CrawlerTaskRun,
    *,
    scheduled_at=None,
) -> CrawlerTaskRun:
    if failed_run.status not in {"FAILED", "TIMED_OUT", "LOST"}:
        raise RunCreationError("只有失败、超时或丢失任务可以重试")
    if failed_run.attempt >= failed_run.max_attempts:
        raise RunCreationError("已达到最大重试次数")
    existing = db.scalar(select(CrawlerTaskRun).where(CrawlerTaskRun.parent_run_id == failed_run.run_id))
    if existing:
        return existing
    task = db.get(CrawlerTask, failed_run.task_id)
    entry = db.get(CrawlerSpiderEntry, failed_run.spider_entry_id)
    release = db.get(CrawlerSpiderRelease, failed_run.spider_release_id)
    if not task or task.status != "ENABLED":
        raise RunCreationError("原任务不存在或已停用")
    if not entry or not release:
        raise RunCreationError("原运行绑定的 SpiderRelease 或 SpiderEntry 不存在")

    server = choose_server(db, task.task_id, entry.image_profile)
    now = utcnow()
    attempt = failed_run.attempt + 1
    task_spec = dict(failed_run.task_spec_json or {})
    task_spec.update({
        "run_id": "pending",
        "attempt": attempt,
        "max_attempts": failed_run.max_attempts,
        "triggered_by": "retry",
        "triggered_by_user_id": None,
        "created_at": now.isoformat().replace("+00:00", "Z") if now.tzinfo else now.isoformat() + "Z",
    })
    run = CrawlerTaskRun(
        run_no=make_run_no(),
        company_id=failed_run.company_id,
        project_id=failed_run.project_id,
        task_id=failed_run.task_id,
        schedule_id=failed_run.schedule_id,
        server_id=server.server_id,
        spider_release_id=failed_run.spider_release_id,
        spider_entry_id=failed_run.spider_entry_id,
        trigger_type="RETRY",
        scheduled_at=scheduled_at or now,
        queued_at=now,
        status="QUEUED",
        attempt=attempt,
        max_attempts=failed_run.max_attempts,
        parent_run_id=failed_run.run_id,
        root_run_id=failed_run.root_run_id or failed_run.run_id,
        image_name=failed_run.image_name,
        image_tag=failed_run.image_tag,
        image_digest=failed_run.image_digest,
        git_commit=failed_run.git_commit,
        task_spec_json=task_spec,
        resource_manifest_json=dict(failed_run.resource_manifest_json or {}),
        runtime_json=dict(failed_run.runtime_json or {}),
        log_path="",
    )
    db.add(run)
    db.flush()
    run.task_spec_json = {**task_spec, "run_id": str(run.run_id)}
    run.log_path = str(build_log_path(task.task_id, run.run_no, now.date().isoformat()))
    db.flush()
    return run

