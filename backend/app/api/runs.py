from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import CrawlerContainerEvent, CrawlerTask, CrawlerTaskRun, SysUser
from app.services.audit import write_operation_log
from app.services.log_service import read_tail, stream_file
from app.utils import utcnow

router = APIRouter(prefix="/runs", tags=["执行记录"])


def run_dict(row: CrawlerTaskRun, task_name: str = "") -> dict:
    return {
        "run_id": row.run_id,
        "run_no": row.run_no,
        "task_id": row.task_id,
        "task_name": task_name,
        "schedule_id": row.schedule_id,
        "server_id": row.server_id,
        "agent_id": row.agent_id,
        "trigger_type": row.trigger_type,
        "triggered_by": row.triggered_by,
        "scheduled_at": row.scheduled_at,
        "queued_at": row.queued_at,
        "claimed_at": row.claimed_at,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "desired_action": row.desired_action,
        "attempt": row.attempt,
        "parent_run_id": row.parent_run_id,
        "container_id": row.container_id,
        "container_name": row.container_name,
        "image_name": row.image_name,
        "image_tag": row.image_tag,
        "image_digest": row.image_digest,
        "git_commit": row.git_commit,
        "exit_code": row.exit_code,
        "duration_ms": row.duration_ms,
        "error_type": row.error_type,
        "error_message": row.error_message,
        "log_path": row.log_path,
        "log_size_bytes": row.log_size_bytes,
        "last_log_at": row.last_log_at,
        "heartbeat_at": row.heartbeat_at,
        "created_at": row.created_at,
    }


@router.get("")
def list_runs(
    task_id: int | None = None,
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=200),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_user),
) -> dict:
    conditions = []
    if task_id:
        conditions.append(CrawlerTaskRun.task_id == task_id)
    if status:
        conditions.append(CrawlerTaskRun.status == status)
    stmt = select(CrawlerTaskRun)
    count_stmt = select(func.count(CrawlerTaskRun.run_id))
    if conditions:
        stmt = stmt.where(*conditions)
        count_stmt = count_stmt.where(*conditions)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(CrawlerTaskRun.run_id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    task_names = {item.task_id: item.task_name for item in db.scalars(select(CrawlerTask).where(CrawlerTask.task_id.in_({row.task_id for row in rows}))).all()} if rows else {}
    return {
        "total": total,
        "items": [run_dict(row, task_names.get(row.task_id, "")) for row in rows],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), _: SysUser = Depends(get_current_user)) -> dict:
    row = db.get(CrawlerTaskRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    task = db.get(CrawlerTask, row.task_id)
    events = db.scalars(
        select(CrawlerContainerEvent).where(CrawlerContainerEvent.run_id == run_id).order_by(CrawlerContainerEvent.event_id.asc())
    ).all()
    result = run_dict(row, task.task_name if task else "")
    result["inspect_summary"] = row.inspect_summary
    result["events"] = [
        {
            "event_type": event.event_type,
            "event_action": event.event_action,
            "container_id": event.container_id,
            "exit_code": event.exit_code,
            "event_message": event.event_message,
            "occurred_at": event.occurred_at,
        }
        for event in events
    ]
    return result


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(require_admin),
) -> dict:
    row = db.get(CrawlerTaskRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    if row.status in {"SUCCESS", "FAILED", "TIMEOUT", "CANCELLED", "LOST", "SKIPPED"}:
        raise HTTPException(status_code=409, detail="该运行实例已经结束")
    if row.status in {"QUEUED", "RETRY_WAIT"}:
        row.status = "CANCELLED"
        row.finished_at = utcnow()
    else:
        row.desired_action = "STOP"
    write_operation_log(db, request, user, "CANCEL_RUN", "RUN", row.run_id, after_data={"status": row.status, "desired_action": row.desired_action})
    db.commit()
    return {"run_id": row.run_id, "status": row.status, "desired_action": row.desired_action}


@router.get("/{run_id}/logs", response_class=PlainTextResponse)
def get_logs(
    run_id: int,
    max_bytes: int = Query(default=512 * 1024, ge=1024, le=5 * 1024 * 1024),
    db: Session = Depends(get_db),
    _: SysUser = Depends(get_current_user),
) -> str:
    row = db.get(CrawlerTaskRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    return read_tail(Path(row.log_path), max_bytes=max_bytes)


@router.get("/{run_id}/logs/stream")
async def stream_logs(run_id: int, db: Session = Depends(get_db), _: SysUser = Depends(get_current_user)) -> StreamingResponse:
    row = db.get(CrawlerTaskRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    return StreamingResponse(stream_file(Path(row.log_path)), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
