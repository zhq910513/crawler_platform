from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import (
    CrawlerImageVersion,
    CrawlerTask,
    CrawlerTaskRuntime,
    CrawlerTaskRun,
    CrawlerTaskSchedule,
    CrawlerTaskTarget,
    SysUser,
)
from app.schemas import TaskCreate, TaskScheduleUpdate
from app.services.audit import write_operation_log
from app.services.cron_service import next_run_utc, validate_cron
from app.services.run_service import RunCreationError, create_run, task_query_with_relations

router = APIRouter(prefix="/tasks", tags=["任务"])


def task_dict(task: CrawlerTask, latest_run: CrawlerTaskRun | None = None) -> dict:
    runtime = task.runtime
    schedule = task.schedule
    return {
        "task_id": task.task_id,
        "task_code": task.task_code,
        "task_name": task.task_name,
        "project_id": task.project_id,
        "platform": task.platform,
        "task_group": task.task_group,
        "developer": task.developer,
        "executor_type": task.executor_type,
        "entrypoint": task.entrypoint,
        "arguments": task.arguments,
        "keyword_arguments": task.keyword_arguments,
        "related_tables": task.related_tables,
        "status": task.status,
        "description": task.description,
        "server_ids": [target.server_id for target in task.targets if target.enabled],
        "runtime": {
            "image_policy": runtime.image_policy,
            "fixed_image_version_id": runtime.fixed_image_version_id,
            "release_channel": runtime.release_channel,
            "pull_policy": runtime.pull_policy,
            "container_command": runtime.container_command,
            "container_working_dir": runtime.container_working_dir,
            "environment_variables": runtime.environment_variables,
            "secret_refs": runtime.secret_refs,
            "volume_mounts": runtime.volume_mounts,
            "network_mode": runtime.network_mode,
            "cpu_limit": float(runtime.cpu_limit),
            "memory_limit_mb": runtime.memory_limit_mb,
            "shm_size_mb": runtime.shm_size_mb,
            "pids_limit": runtime.pids_limit,
            "stop_grace_seconds": runtime.stop_grace_seconds,
            "auto_remove": runtime.auto_remove,
            "keep_failed_container": runtime.keep_failed_container,
        } if runtime else None,
        "schedule": {
            "schedule_id": schedule.schedule_id,
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
            "last_triggered_at": schedule.last_triggered_at,
        } if schedule else None,
        "latest_run": {
            "run_id": latest_run.run_id,
            "run_no": latest_run.run_no,
            "status": latest_run.status,
            "started_at": latest_run.started_at,
            "finished_at": latest_run.finished_at,
            "duration_ms": latest_run.duration_ms,
        } if latest_run else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def validate_task_payload(db: Session, payload: TaskCreate) -> None:
    if payload.schedule.schedule_type == "CRON":
        validate_cron(payload.schedule.cron_expression, payload.schedule.timezone)
    if payload.runtime.image_policy == "PINNED":
        if not payload.runtime.fixed_image_version_id:
            raise HTTPException(status_code=400, detail="固定镜像策略必须选择镜像版本")
        image = db.get(CrawlerImageVersion, payload.runtime.fixed_image_version_id)
        if not image or image.project_id != payload.project_id or image.build_status != "SUCCESS":
            raise HTTPException(status_code=400, detail="所选镜像版本不属于该项目或构建未成功")


@router.get("")
def list_tasks(
    keyword: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_user),
) -> dict:
    stmt = task_query_with_relations()
    count_stmt = select(func.count(CrawlerTask.task_id))
    conditions = []
    if keyword:
        conditions.append(or_(CrawlerTask.task_name.like(f"%{keyword}%"), CrawlerTask.task_code.like(f"%{keyword}%"), CrawlerTask.platform.like(f"%{keyword}%")))
    if status:
        conditions.append(CrawlerTask.status == status)
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    tasks = db.scalars(stmt.order_by(CrawlerTask.task_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = []
    for task in tasks:
        latest = db.scalar(
            select(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task.task_id).order_by(CrawlerTaskRun.run_id.desc()).limit(1)
        )
        items.append(task_dict(task, latest))
    return {"total": total, "items": items, "page": page, "page_size": page_size}


@router.get("/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db), _: SysUser = Depends(get_current_user)) -> dict:
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    latest = db.scalar(select(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task_id).order_by(CrawlerTaskRun.run_id.desc()).limit(1))
    return task_dict(task, latest)


@router.post("")
def create_task_api(
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    if db.scalar(select(CrawlerTask).where(CrawlerTask.task_code == payload.task_code)):
        raise HTTPException(status_code=409, detail="任务编码已存在")
    validate_task_payload(db, payload)
    core = payload.model_dump(exclude={"runtime", "schedule", "server_ids"})
    task = CrawlerTask(**core, created_by=user.user_id, updated_by=user.user_id)
    db.add(task)
    db.flush()
    runtime = CrawlerTaskRuntime(task_id=task.task_id, **payload.runtime.model_dump())
    schedule_values = payload.schedule.model_dump()
    if schedule_values["schedule_type"] == "CRON" and schedule_values["enabled"]:
        schedule_values["next_run_at"] = next_run_utc(schedule_values["cron_expression"], schedule_values["timezone"])
    schedule = CrawlerTaskSchedule(task_id=task.task_id, **schedule_values)
    db.add_all([runtime, schedule])
    db.add_all([CrawlerTaskTarget(task_id=task.task_id, server_id=server_id, priority=index * 10 + 10) for index, server_id in enumerate(payload.server_ids)])
    db.flush()
    write_operation_log(db, request, user, "CREATE", "TASK", task.task_id, after_data={"task_code": task.task_code, "task_name": task.task_name})
    db.commit()
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task.task_id))
    return task_dict(task)


@router.put("/{task_id}")
def update_task_api(
    task_id: int,
    payload: TaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    duplicate = db.scalar(select(CrawlerTask).where(CrawlerTask.task_code == payload.task_code, CrawlerTask.task_id != task_id))
    if duplicate:
        raise HTTPException(status_code=409, detail="任务编码已存在")
    validate_task_payload(db, payload)
    before = {"task_code": task.task_code, "task_name": task.task_name, "entrypoint": task.entrypoint}
    core = payload.model_dump(exclude={"runtime", "schedule", "server_ids"})
    for key, value in core.items():
        setattr(task, key, value)
    task.updated_by = user.user_id
    if not task.runtime:
        task.runtime = CrawlerTaskRuntime(task_id=task.task_id)
    for key, value in payload.runtime.model_dump().items():
        setattr(task.runtime, key, value)
    if not task.schedule:
        task.schedule = CrawlerTaskSchedule(task_id=task.task_id)
    schedule_values = payload.schedule.model_dump()
    for key, value in schedule_values.items():
        setattr(task.schedule, key, value)
    task.schedule.next_run_at = next_run_utc(task.schedule.cron_expression, task.schedule.timezone) if task.schedule.schedule_type == "CRON" and task.schedule.enabled else None
    for target in list(task.targets):
        db.delete(target)
    db.flush()
    db.add_all([CrawlerTaskTarget(task_id=task.task_id, server_id=server_id, priority=index * 10 + 10) for index, server_id in enumerate(payload.server_ids)])
    write_operation_log(db, request, user, "UPDATE", "TASK", task.task_id, before_data=before, after_data={"task_code": task.task_code, "task_name": task.task_name, "entrypoint": task.entrypoint})
    db.commit()
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task_id))
    return task_dict(task)


@router.patch("/{task_id}/schedule")
def update_schedule(
    task_id: int,
    payload: TaskScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task_id))
    if not task or not task.schedule:
        raise HTTPException(status_code=404, detail="任务或调度配置不存在")
    before = {
        "cron_expression": task.schedule.cron_expression,
        "timezone": task.schedule.timezone,
        "misfire_policy": task.schedule.misfire_policy,
        "enabled": task.schedule.enabled,
    }
    values = payload.model_dump(exclude_none=True)
    cron_value = values.get("cron_expression", task.schedule.cron_expression)
    timezone_value = values.get("timezone", task.schedule.timezone)
    if task.schedule.schedule_type == "CRON":
        validate_cron(cron_value, timezone_value)
    for key, value in values.items():
        setattr(task.schedule, key, value)
    task.schedule.next_run_at = next_run_utc(task.schedule.cron_expression, task.schedule.timezone) if task.schedule.schedule_type == "CRON" and task.schedule.enabled else None
    after = {
        "cron_expression": task.schedule.cron_expression,
        "timezone": task.schedule.timezone,
        "misfire_policy": task.schedule.misfire_policy,
        "enabled": task.schedule.enabled,
    }
    write_operation_log(db, request, user, "UPDATE_SCHEDULE", "TASK", task.task_id, before, after)
    db.commit()
    return after | {"next_run_at": task.schedule.next_run_at}


@router.post("/{task_id}/run")
def run_once(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    task = db.scalar(task_query_with_relations().where(CrawlerTask.task_id == task_id))
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    try:
        run = create_run(db, task, trigger_type="MANUAL", triggered_by=user.user_id)
    except RunCreationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    write_operation_log(db, request, user, "RUN_NOW", "TASK", task.task_id, after_data={"run_no": run.run_no})
    db.commit()
    return {"run_id": run.run_id, "run_no": run.run_no, "status": run.status}


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    task = db.get(CrawlerTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    active = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.task_id == task_id, CrawlerTaskRun.status.in_(["CLAIMED", "STARTING", "RUNNING"]))) or 0
    if active:
        raise HTTPException(status_code=409, detail="任务存在运行中的实例，不能删除")
    before = {"task_code": task.task_code, "task_name": task.task_name}
    db.delete(task)
    write_operation_log(db, request, user, "DELETE", "TASK", task_id, before_data=before)
    db.commit()
    return {"ok": True}
