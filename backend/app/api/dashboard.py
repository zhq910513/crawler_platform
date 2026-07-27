from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_admin
from app.models import CrawlerAgent, CrawlerServer, CrawlerTask, CrawlerTaskRun, SysUser
from app.utils import utcnow

router = APIRouter(prefix="/dashboard", tags=["首页"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _: SysUser = Depends(require_admin)) -> dict:
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    task_total = db.scalar(select(func.count(CrawlerTask.task_id))) or 0
    running = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.status.in_(["CLAIMED", "STARTING", "RUNNING"]))) or 0
    success_today = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.status == "SUCCESS", CrawlerTaskRun.finished_at >= today)) or 0
    failed_today = db.scalar(select(func.count(CrawlerTaskRun.run_id)).where(CrawlerTaskRun.status.in_(["FAILED", "TIMEOUT", "LOST"]), CrawlerTaskRun.finished_at >= today)) or 0
    server_total = db.scalar(select(func.count(CrawlerServer.server_id))) or 0
    online_agents = db.scalar(select(func.count(CrawlerAgent.agent_id)).where(CrawlerAgent.last_heartbeat_at >= now - timedelta(seconds=90))) or 0
    recent_failed = db.execute(
        select(CrawlerTaskRun, CrawlerTask.task_name)
        .join(CrawlerTask, CrawlerTask.task_id == CrawlerTaskRun.task_id)
        .where(CrawlerTaskRun.status.in_(["FAILED", "TIMEOUT", "LOST"]))
        .order_by(CrawlerTaskRun.run_id.desc())
        .limit(10)
    ).all()
    return {
        "task_total": task_total,
        "running": running,
        "success_today": success_today,
        "failed_today": failed_today,
        "server_total": server_total,
        "server_online": online_agents,
        "recent_failed": [
            {
                "run_id": run.run_id,
                "run_no": run.run_no,
                "task_name": task_name,
                "status": run.status,
                "error_message": run.error_message,
                "finished_at": run.finished_at,
            }
            for run, task_name in recent_failed
        ],
    }
