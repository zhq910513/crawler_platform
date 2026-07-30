from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.deps import get_current_user
from app.models import CrawlerProjectMember, CrawlerTask, CrawlerTaskRun, CrawlerTaskRunEvent, SysUser
from app.services.audit import write_operation_log
from app.services.log_service import read_tail, stream_file_from_offset
from app.services.permissions import is_super_admin, require_project_role, visible_project_ids
from app.services.run_service import RunCreationError, create_retry
from app.services.run_state import ACTIVE_STATUSES, TERMINAL_STATUSES, InvalidRunTransition, transition

router = APIRouter(prefix="/runs", tags=["运行记录"])


def _run_dict(row: CrawlerTaskRun) -> dict[str, Any]:
    return {
        "run_id": row.run_id,
        "run_no": row.run_no,
        "company_id": row.company_id,
        "project_id": row.project_id,
        "task_id": row.task_id,
        "status": row.status,
        "trigger_type": row.trigger_type,
        "attempt": row.attempt,
        "max_attempts": row.max_attempts,
        "parent_run_id": row.parent_run_id,
        "root_run_id": row.root_run_id,
        "server_id": row.server_id,
        "agent_id": row.agent_id,
        "container_id": row.container_id,
        "container_name": row.container_name,
        "image_name": row.image_name,
        "image_tag": row.image_tag,
        "image_digest": row.image_digest,
        "git_commit": row.git_commit,
        "queued_at": row.queued_at,
        "assigned_at": row.assigned_at,
        "starting_at": row.starting_at,
        "started_at": row.started_at,
        "cancel_requested_at": row.cancel_requested_at,
        "finished_at": row.finished_at,
        "duration_ms": row.duration_ms,
        "exit_code": row.exit_code,
        "oom_killed": row.oom_killed,
        "last_error": {
            "event_id": row.last_error_event_id,
            "code": row.last_error_code,
            "type": row.last_error_type,
            "message": row.last_error_message,
            "occurred_at": row.last_error_at,
            "log_seq": row.last_error_log_seq,
        } if row.last_error_message else None,
        "terminal_error": {
            "code": row.terminal_error_code,
            "type": row.terminal_error_type,
            "message": row.terminal_error_message,
            "retryable": row.terminal_error_retryable,
            "details": row.terminal_error_json,
        } if row.terminal_error_message else None,
        "result": row.result_json,
        "metrics": row.metrics_json,
        "task_spec": row.task_spec_json,
        "runtime": row.runtime_json,
        "inspect_summary": row.inspect_summary,
        "log_size_bytes": row.log_size_bytes,
        "last_log_at": row.last_log_at,
        "created_at": row.created_at,
    }


def _get_visible_run(db: Session, user: SysUser, run_id: int) -> CrawlerTaskRun:
    row = db.get(CrawlerTaskRun, run_id)
    if not row:
        raise HTTPException(status_code=404, detail="运行实例不存在")
    require_project_role(db, user, int(row.project_id), "VIEWER")
    return row


@router.get("")
def list_runs(
    project_id: int | None = None,
    task_id: int | None = None,
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    conditions = []
    ids = visible_project_ids(db, user)
    if ids is not None:
        conditions.append(CrawlerTaskRun.project_id.in_(ids or [-1]))
    if project_id:
        require_project_role(db, user, project_id, "VIEWER")
        conditions.append(CrawlerTaskRun.project_id == project_id)
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
    return {"total": total, "items": [_run_dict(row) for row in rows], "page": page, "page_size": page_size}


@router.get("/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db), user: SysUser = Depends(get_current_user)) -> dict:
    row = _get_visible_run(db, user, run_id)
    events = db.scalars(select(CrawlerTaskRunEvent).where(
        CrawlerTaskRunEvent.run_id == run_id,
        CrawlerTaskRunEvent.level.in_(["ERROR", "CRITICAL"]),
    ).order_by(CrawlerTaskRunEvent.event_id.desc()).limit(50)).all()
    result = _run_dict(row)
    result["recent_errors"] = [{
        "event_id": x.event_id,
        "event_uid": x.event_uid,
        "level": x.level,
        "event_name": x.event_name,
        "message": x.message,
        "error_code": x.error_code,
        "error_type": x.error_type,
        "retryable": x.retryable,
        "occurred_at": x.occurred_at,
    } for x in reversed(events)]
    return result


@router.get("/{run_id}/logs")
def get_logs(
    run_id: int,
    max_bytes: int = Query(default=512 * 1024, ge=1024, le=5 * 1024 * 1024),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    row = _get_visible_run(db, user, run_id)
    content, offset = read_tail(Path(row.log_path), max_bytes=max_bytes)
    return {"content": content, "offset": offset, "size": row.log_size_bytes}


def _sse(event: str, data: dict[str, Any], event_id: int | None = None) -> str:
    prefix = f"id: {event_id}\n" if event_id is not None else ""
    return f"{prefix}event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _user_still_has_access(db: Session, user_id: int, is_admin: bool, project_id: int) -> bool:
    if is_admin:
        return True
    return bool(db.scalar(select(func.count()).select_from(CrawlerProjectMember).where(
        CrawlerProjectMember.user_id == user_id,
        CrawlerProjectMember.project_id == project_id,
    )))


@router.get("/{run_id}/events/stream")
def event_stream(
    run_id: int,
    request: Request,
    after_event_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> StreamingResponse:
    row = _get_visible_run(db, user, run_id)
    project_id = int(row.project_id)
    user_id = user.user_id
    admin = is_super_admin(user)

    async def generate() -> AsyncIterator[str]:
        cursor = after_event_id
        last_snapshot = ""
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            with SessionLocal() as session:
                if not _user_still_has_access(session, user_id, admin, project_id):
                    yield _sse("stream_closed", {"reason": "permission_revoked"})
                    return
                current = session.get(CrawlerTaskRun, run_id)
                if not current:
                    yield _sse("stream_closed", {"reason": "run_not_found"})
                    return
                events = session.scalars(select(CrawlerTaskRunEvent).where(
                    CrawlerTaskRunEvent.run_id == run_id,
                    CrawlerTaskRunEvent.event_id > cursor,
                ).order_by(CrawlerTaskRunEvent.event_id).limit(200)).all()
                for item in events:
                    cursor = item.event_id
                    yield _sse("run_event", {
                        "event_id": item.event_id,
                        "event_uid": item.event_uid,
                        "level": item.level,
                        "event_name": item.event_name,
                        "message": item.message,
                        "error_code": item.error_code,
                        "error_type": item.error_type,
                        "retryable": item.retryable,
                        "context": item.context_json,
                        "occurred_at": item.occurred_at,
                    }, item.event_id)
                snapshot = _run_dict(current)
                snapshot_key = json.dumps(snapshot, default=str, sort_keys=True, ensure_ascii=False)
                if snapshot_key != last_snapshot:
                    last_snapshot = snapshot_key
                    yield _sse("run_snapshot", snapshot)
                    idle = 0
                else:
                    idle += 1
                if current.status in TERMINAL_STATUSES and not events and idle >= 4:
                    yield _sse("stream_closed", {"status": current.status})
                    return
            if idle and idle % max(1, int(settings.sse_keepalive_seconds / settings.sse_poll_seconds)) == 0:
                yield ": keepalive\n\n"
            await asyncio.sleep(settings.sse_poll_seconds)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{run_id}/logs/stream")
def logs_stream(
    run_id: int,
    request: Request,
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> StreamingResponse:
    row = _get_visible_run(db, user, run_id)
    path = Path(row.log_path)
    project_id = int(row.project_id)
    user_id = user.user_id
    admin = is_super_admin(user)

    async def generate() -> AsyncIterator[str]:
        last_check = 0
        async for next_offset, line in stream_file_from_offset(path, offset, settings.sse_poll_seconds):
            if await request.is_disconnected():
                return
            yield _sse("log", {"offset": next_offset, "line": line})
            last_check += 1
            if last_check % 100 == 0:
                with SessionLocal() as session:
                    if not _user_still_has_access(session, user_id, admin, project_id):
                        yield _sse("stream_closed", {"reason": "permission_revoked"})
                        return
                    current = session.get(CrawlerTaskRun, run_id)
                    if not current:
                        return
            # stream_file 本身在空闲时等待；终态关闭由事件流负责，日志流允许继续等最后落盘内容。

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/{run_id}/cancel")
def cancel_run(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    row = _get_visible_run(db, user, run_id)
    require_project_role(db, user, int(row.project_id), "OPERATOR")
    if row.status in TERMINAL_STATUSES:
        return {"ok": True, "status": row.status}
    if row.status in {"CREATED", "QUEUED"}:
        transition(row, "CANCELLED")
    else:
        transition(row, "CANCEL_REQUESTED")
        row.desired_action = "STOP"
    write_operation_log(db, request, user, "CANCEL", "RUN", run_id)
    db.commit()
    return {"ok": True, "status": row.status}


@router.post("/{run_id}/retry")
def retry_run(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    row = _get_visible_run(db, user, run_id)
    require_project_role(db, user, int(row.project_id), "OPERATOR")
    try:
        child = create_retry(db, row)
    except RunCreationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    write_operation_log(db, request, user, "RETRY", "RUN", run_id, after_data={"new_run_id": child.run_id})
    db.commit()
    return {"run_id": child.run_id, "run_no": child.run_no, "status": child.status}
