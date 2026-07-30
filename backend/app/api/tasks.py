from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    CrawlerProject,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerSpiderEntry,
    CrawlerSpiderRelease,
    CrawlerTask,
    CrawlerTaskChangeLog,
    CrawlerTaskRun,
    CrawlerTaskRuntime,
    CrawlerTaskSchedule,
    CrawlerTaskTarget,
    SysUser,
)
from app.schemas import TaskCreate, TaskScheduleUpdate
from app.services.audit import write_operation_log
from app.services.cron_service import next_run_utc, validate_cron
from app.services.permissions import project_role, require_project_role, visible_project_ids
from app.services.release_service import ReleaseValidationError, ensure_latest_selectable_release
from app.services.run_service import ACTIVE_RUN_STATUSES, RunCreationError, create_run

router = APIRouter(prefix="/tasks", tags=["任务"])


def _task_query():
    return select(CrawlerTask).options(
        selectinload(CrawlerTask.runtime),
        selectinload(CrawlerTask.schedule),
        selectinload(CrawlerTask.targets),
    )


def _task_dict(db: Session, task: CrawlerTask, user: SysUser, latest: CrawlerTaskRun | None = None) -> dict:
    runtime = task.runtime
    schedule = task.schedule
    return {
        "task_id": task.task_id,
        "company_id": task.company_id,
        "project_id": task.project_id,
        "task_code": task.task_code,
        "task_name": task.task_name,
        "spider_task_name": task.spider_task_name,
        "platform": task.platform,
        "task_group": task.task_group,
        "developer": task.developer,
        "entry_module": task.entry_module,
        "entry_function": task.entry_function,
        "source_type": task.source_type,
        "source_file": task.source_file,
        "source_fingerprint": task.source_fingerprint,
        "resource_requirements": task.resource_requirements,
        "parameters": task.parameters,
        "status": task.status,
        "description": task.description,
        "project_role": project_role(db, user, task.project_id),
        "server_ids": [x.server_id for x in task.targets],
        "runtime": {
            "image_policy": runtime.image_policy,
            "fixed_spider_release_id": runtime.fixed_spider_release_id,
            "release_channel": runtime.release_channel,
            "pull_policy": runtime.pull_policy,
            "cpu_limit": float(runtime.cpu_limit),
            "memory_limit_mb": runtime.memory_limit_mb,
            "shm_size_mb": runtime.shm_size_mb,
            "pids_limit": runtime.pids_limit,
            "stop_grace_seconds": runtime.stop_grace_seconds,
            "auto_remove": runtime.auto_remove,
            "keep_failed_container": runtime.keep_failed_container,
        } if runtime else None,
        "schedule": {
            "schedule_type": schedule.schedule_type,
            "cron_expression": schedule.cron_expression,
            "timezone": schedule.timezone,
            "misfire_policy": schedule.misfire_policy,
            "max_concurrency": schedule.max_concurrency,
            "overlap_policy": schedule.overlap_policy,
            "timeout_seconds": schedule.timeout_seconds,
            "max_retry_count": schedule.max_retry_count,
            "retry_interval_seconds": schedule.retry_interval_seconds,
            "retry_backoff": schedule.retry_backoff,
            "enabled": schedule.enabled,
            "next_run_at": schedule.next_run_at,
        } if schedule else None,
        "latest_run": {
            "run_id": latest.run_id,
            "run_no": latest.run_no,
            "status": latest.status,
            "last_error_message": latest.last_error_message,
            "started_at": latest.started_at,
            "finished_at": latest.finished_at,
        } if latest else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def _resolve_release_id(db: Session, payload: TaskCreate) -> int:
    if payload.runtime.image_policy == "PINNED":
        release = db.get(CrawlerSpiderRelease, int(payload.runtime.fixed_spider_release_id))
        if not release or release.status != "ACTIVE":
            raise HTTPException(status_code=400, detail="固定版本不可用")
        try:
            ensure_latest_selectable_release(db, release)
        except ReleaseValidationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return release.release_id
    channel = db.scalar(select(CrawlerReleaseChannel).where(
        CrawlerReleaseChannel.project_id == payload.project_id,
        CrawlerReleaseChannel.channel_name == payload.runtime.release_channel,
    ))
    if not channel or not channel.spider_release_id:
        raise HTTPException(status_code=400, detail="项目发布通道未绑定 SpiderRelease")
    return channel.spider_release_id


def _validate_payload(db: Session, payload: TaskCreate) -> CrawlerProject:
    project = db.get(CrawlerProject, payload.project_id)
    if not project or not project.company_id:
        raise HTTPException(status_code=404, detail="项目不存在或未绑定公司")
    release_id = _resolve_release_id(db, payload)
    entry = db.scalar(select(CrawlerSpiderEntry).where(
        CrawlerSpiderEntry.release_id == release_id,
        CrawlerSpiderEntry.task_name == payload.spider_task_name,
    ))
    if not entry:
        raise HTTPException(status_code=400, detail="所选发布版本不包含该 SpiderEntry")
    if payload.schedule.schedule_type == "CRON":
        validate_cron(payload.schedule.cron_expression, payload.schedule.timezone)
    if not payload.server_ids:
        raise HTTPException(status_code=400, detail="至少绑定一台 Agent 服务器")
    count = db.scalar(select(func.count()).select_from(CrawlerServer).where(CrawlerServer.server_id.in_(payload.server_ids))) or 0
    if count != len(set(payload.server_ids)):
        raise HTTPException(status_code=400, detail="存在无效 Agent 服务器")
    return project


@router.get("")
def list_tasks(
    project_id: int | None = None,
    keyword: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    stmt = _task_query()
    count_stmt = select(func.count(CrawlerTask.task_id))
    conditions = []
    ids = visible_project_ids(db, user)
    if ids is not None:
        conditions.append(CrawlerTask.project_id.in_(ids or [-1]))
    if project_id:
        require_project_role(db, user, project_id, "VIEWER")
        conditions.append(CrawlerTask.project_id == project_id)
    if keyword:
        conditions.append(or_(CrawlerTask.task_name.like(f"%{keyword}%"), CrawlerTask.task_code.like(f"%{keyword}%"), CrawlerTask.spider_task_name.like(f"%{keyword}%")))
    if status:
        conditions.append(CrawlerTask.status == status)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(CrawlerTask.task_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for task in rows:
        latest = db.scalar(select(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task.task_id).order_by(CrawlerTaskRun.run_id.desc()).limit(1))
        items.append(_task_dict(db, task, user, latest))
    return {"total": total, "items": items, "page": page, "page_size": page_size}


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> dict:
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    require_project_role(db, user, task.project_id, "VIEWER")
    latest = db.scalar(select(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task_id).order_by(CrawlerTaskRun.run_id.desc()).limit(1))
    return _task_dict(db, task, user, latest)


def _save_task(
    db: Session,
    task: CrawlerTask,
    payload: TaskCreate,
    user: SysUser,
    project: CrawlerProject | None = None,
) -> None:
    project = project or _validate_payload(db, payload)
    values = payload.model_dump(exclude={"runtime", "schedule", "server_ids"})
    for key, value in values.items():
        setattr(task, key, value)
    task.company_id = project.company_id
    task.executor_type = "SPIDER_ENTRY"
    task.entrypoint = ""
    task.arguments = []
    task.keyword_arguments = {}
    task.updated_by = user.user_id
    if not task.runtime:
        task.runtime = CrawlerTaskRuntime(task_id=task.task_id)
    runtime_values = payload.runtime.model_dump()
    runtime_values["fixed_image_version_id"] = None
    for key, value in runtime_values.items():
        setattr(task.runtime, key, value)
    task.runtime.container_command = []
    task.runtime.container_working_dir = ""
    task.runtime.environment_variables = {}
    task.runtime.secret_refs = {}
    task.runtime.volume_mounts = []
    task.runtime.network_mode = "bridge"
    if not task.schedule:
        task.schedule = CrawlerTaskSchedule(task_id=task.task_id)
    for key, value in payload.schedule.model_dump().items():
        setattr(task.schedule, key, value)
    task.schedule.next_run_at = (
        next_run_utc(task.schedule.cron_expression, task.schedule.timezone)
        if task.schedule.schedule_type == "CRON" and task.schedule.enabled else None
    )
    for target in list(task.targets):
        db.delete(target)
    db.flush()
    db.add_all([CrawlerTaskTarget(task_id=task.task_id, server_id=server_id, priority=index * 10 + 10) for index, server_id in enumerate(payload.server_ids)])


@router.post("")
def create_task(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    require_project_role(db, user, payload.project_id, "OWNER")
    if db.scalar(select(CrawlerTask).where(CrawlerTask.task_code == payload.task_code)):
        raise HTTPException(status_code=409, detail="任务编码已存在")
    project = _validate_payload(db, payload)
    task = CrawlerTask(
        company_id=project.company_id,
        task_code=payload.task_code,
        task_name=payload.task_name,
        project_id=payload.project_id,
        created_by=user.user_id,
        updated_by=user.user_id,
    )
    db.add(task)
    db.flush()
    _save_task(db, task, payload, user, project)
    write_operation_log(db, request, user, "CREATE", "TASK", task.task_id, after_data={"task_code": task.task_code, "spider_task_name": task.spider_task_name})
    db.commit()
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task.task_id))
    return _task_dict(db, task, user)


@router.put("/{task_id}")
def update_task(
    task_id: int,
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    require_project_role(db, user, task.project_id, "OWNER")
    if payload.project_id != task.project_id:
        raise HTTPException(status_code=409, detail="任务不能跨项目迁移")
    duplicate = db.scalar(select(CrawlerTask).where(CrawlerTask.task_code == payload.task_code, CrawlerTask.task_id != task_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="任务编码已存在")
    _save_task(db, task, payload, user)
    write_operation_log(db, request, user, "UPDATE", "TASK", task_id, after_data={"task_code": task.task_code, "spider_task_name": task.spider_task_name})
    db.commit()
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task_id))
    return _task_dict(db, task, user)


@router.patch("/{task_id}/schedule")
def update_schedule(
    task_id: int,
    payload: TaskScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task_id))
    if not task or not task.schedule:
        raise HTTPException(status_code=404, detail="任务或调度不存在")
    require_project_role(db, user, task.project_id, "OWNER")
    before_schedule = {
        "cron_expression": task.schedule.cron_expression,
        "timezone": task.schedule.timezone,
        "misfire_policy": task.schedule.misfire_policy,
        "max_concurrency": task.schedule.max_concurrency,
        "overlap_policy": task.schedule.overlap_policy,
        "timeout_seconds": task.schedule.timeout_seconds,
        "max_retry_count": task.schedule.max_retry_count,
        "retry_interval_seconds": task.schedule.retry_interval_seconds,
        "retry_backoff": task.schedule.retry_backoff,
        "enabled": task.schedule.enabled,
    }
    values = payload.model_dump(exclude_none=True)
    for key, value in values.items():
        setattr(task.schedule, key, value)
    if task.schedule.schedule_type == "CRON":
        validate_cron(task.schedule.cron_expression, task.schedule.timezone)
    task.schedule.next_run_at = next_run_utc(task.schedule.cron_expression, task.schedule.timezone) if task.schedule.schedule_type == "CRON" and task.schedule.enabled else None
    after_schedule = before_schedule | values | {"next_run_at": task.schedule.next_run_at}
    db.add(CrawlerTaskChangeLog(
        task_id=task.task_id,
        project_id=task.project_id,
        user_id=user.user_id,
        change_type="UPDATE_SCHEDULE",
        before_json=before_schedule,
        after_json=after_schedule,
        reason="前端平台调度修改；生产真实调度以前端配置为准",
    ))
    write_operation_log(db, request, user, "UPDATE_SCHEDULE", "TASK", task_id, after_data=values)
    db.commit()
    return values | {"next_run_at": task.schedule.next_run_at}


@router.post("/{task_id}/run")
def run_once(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.scalar(_task_query().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    require_project_role(db, user, task.project_id, "OPERATOR")
    try:
        run = create_run(db, task, "MANUAL", triggered_by=user.user_id)
    except RunCreationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_operation_log(db, request, user, "RUN_NOW", "TASK", task_id, after_data={"run_no": run.run_no})
    db.commit()
    return {"run_id": run.run_id, "run_no": run.run_no, "status": run.status}


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.get(CrawlerTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    require_project_role(db, user, task.project_id, "OWNER")
    active = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.task_id == task_id, CrawlerTaskRun.status.in_(ACTIVE_RUN_STATUSES))) or 0
    if active:
        raise HTTPException(status_code=409, detail="任务存在运行实例，不能删除")
    db.delete(task)
    write_operation_log(db, request, user, "DELETE", "TASK", task_id)
    db.commit()
    return {"ok": True}
