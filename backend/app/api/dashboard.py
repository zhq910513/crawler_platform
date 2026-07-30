from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import CrawlerAgent, CrawlerServer, CrawlerTask, CrawlerTaskRun, SysUser
from app.services.permissions import require_project_role, visible_project_ids
from app.services.run_state import ACTIVE_STATUSES
from app.utils import utcnow

router = APIRouter(prefix="/dashboard", tags=["首页"])


@router.get("/summary")
def summary(
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: SysUser = Depends(get_current_user),
) -> dict:
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ids = visible_project_ids(db, user)
    project_conditions = []
    if ids is not None:
        project_conditions.append(CrawlerTask.project_id.in_(ids or [-1]))
    if project_id:
        require_project_role(db, user, project_id, "VIEWER")
        project_conditions.append(CrawlerTask.project_id == project_id)
    task_stmt = select(func.count(CrawlerTask.task_id))
    if project_conditions:
        task_stmt = task_stmt.where(*project_conditions)
    task_total = db.scalar(task_stmt) or 0

    run_conditions = []
    if ids is not None:
        run_conditions.append(CrawlerTaskRun.project_id.in_(ids or [-1]))
    if project_id:
        run_conditions.append(CrawlerTaskRun.project_id == project_id)

    def count_runs(*conditions) -> int:
        stmt = select(func.count(CrawlerTaskRun.run_id)).where(*conditions)
        if run_conditions:
            stmt = stmt.where(*run_conditions)
        return db.scalar(stmt) or 0

    running = count_runs(CrawlerTaskRun.status.in_(ACTIVE_STATUSES))
    success_today = count_runs(CrawlerTaskRun.status.in_(["SUCCEEDED", "PARTIAL_SUCCESS"]), CrawlerTaskRun.finished_at >= today)
    failed_today = count_runs(CrawlerTaskRun.status.in_(["FAILED", "TIMED_OUT", "LOST"]), CrawlerTaskRun.finished_at >= today)
    server_total = db.scalar(select(func.count(CrawlerServer.server_id))) or 0
    online_agents = db.scalar(select(func.count(CrawlerAgent.agent_id)).where(CrawlerAgent.last_heartbeat_at >= now - timedelta(seconds=settings.agent_offline_seconds))) or 0
    recent_stmt = (
        select(CrawlerTaskRun, CrawlerTask.task_name)
        .join(CrawlerTask, CrawlerTask.task_id == CrawlerTaskRun.task_id)
        .where(CrawlerTaskRun.status.in_(["FAILED", "TIMED_OUT", "LOST"]))
    )
    if run_conditions:
        recent_stmt = recent_stmt.where(*run_conditions)
    rows = db.execute(recent_stmt.order_by(CrawlerTaskRun.run_id.desc()).limit(10)).all()
    return {
        "task_total": task_total,
        "running": running,
        "success_today": success_today,
        "failed_today": failed_today,
        "server_total": server_total,
        "server_online": online_agents,
        "recent_failed": [{
            "run_id": run.run_id,
            "run_no": run.run_no,
            "task_name": task_name,
            "status": run.status,
            "error_message": run.terminal_error_message or run.last_error_message,
            "finished_at": run.finished_at,
        } for run, task_name in rows],
    }
