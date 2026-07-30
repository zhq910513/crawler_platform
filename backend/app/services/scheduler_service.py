from __future__ import annotations

import time
import uuid
from datetime import timedelta

import redis
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import SessionLocal
from app.models import CrawlerAgent, CrawlerServer, CrawlerTask, CrawlerTaskRun, CrawlerTaskSchedule
from app.services.cron_service import next_run_utc
from app.services.run_service import RunCreationError, create_retry, create_run
from app.services.run_state import ACTIVE_STATUSES, transition
from app.utils import utcnow


class SchedulerService:
    def __init__(self) -> None:
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.lock_name = "crawler:scheduler:leader:v2"
        self.token = str(uuid.uuid4())

    def acquire_lock(self) -> bool:
        return bool(self.redis.set(self.lock_name, self.token, nx=True, ex=settings.scheduler_lock_seconds))

    def release_lock(self) -> None:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        try:
            self.redis.eval(script, 1, self.lock_name, self.token)
        except Exception:
            pass

    def run_forever(self) -> None:
        print("Scheduler V2 started", flush=True)
        while True:
            try:
                if self.acquire_lock():
                    try:
                        with SessionLocal() as db:
                            self.initialize_schedules(db)
                            self.dispatch_due_schedules(db)
                            self.dispatch_retries(db)
                            self.recover_expired_runs(db)
                            self.mark_offline_agents(db)
                            db.commit()
                    finally:
                        self.release_lock()
            except Exception as exc:
                print(f"Scheduler error: {exc!r}", flush=True)
            time.sleep(settings.scheduler_poll_seconds)

    def initialize_schedules(self, db: Session) -> None:
        rows = db.scalars(select(CrawlerTaskSchedule).where(
            CrawlerTaskSchedule.enabled.is_(True),
            CrawlerTaskSchedule.schedule_type == "CRON",
            CrawlerTaskSchedule.next_run_at.is_(None),
        )).all()
        now = utcnow()
        for row in rows:
            try:
                row.next_run_at = next_run_utc(row.cron_expression, row.timezone, now)
            except Exception:
                row.enabled = False

    def dispatch_due_schedules(self, db: Session) -> None:
        now = utcnow()
        rows = db.scalars(
            select(CrawlerTaskSchedule)
            .options(
                selectinload(CrawlerTaskSchedule.task).selectinload(CrawlerTask.runtime),
                selectinload(CrawlerTaskSchedule.task).selectinload(CrawlerTask.targets),
            )
            .where(
                CrawlerTaskSchedule.enabled.is_(True),
                CrawlerTaskSchedule.schedule_type == "CRON",
                CrawlerTaskSchedule.next_run_at.is_not(None),
                CrawlerTaskSchedule.next_run_at <= now,
            )
            .with_for_update(skip_locked=True)
            .limit(100)
        ).all()
        for schedule in rows:
            scheduled_at = schedule.next_run_at
            if not scheduled_at:
                continue
            late = scheduled_at < now - timedelta(seconds=max(settings.scheduler_poll_seconds * 2, 15))
            if not late or schedule.misfire_policy == "FIRE_ONCE":
                try:
                    with db.begin_nested():
                        create_run(db, schedule.task, "SCHEDULE", scheduled_at=scheduled_at, schedule=schedule)
                except (RunCreationError, IntegrityError) as exc:
                    print(f"Create scheduled run failed task={schedule.task_id}: {exc}", flush=True)
            schedule.last_triggered_at = now
            schedule.next_run_at = next_run_utc(schedule.cron_expression, schedule.timezone, now)

    def dispatch_retries(self, db: Session) -> None:
        now = utcnow()
        rows = db.scalars(select(CrawlerTaskRun).where(
            CrawlerTaskRun.status.in_(["FAILED", "TIMED_OUT", "LOST"]),
            CrawlerTaskRun.finished_at.is_not(None),
            CrawlerTaskRun.attempt < CrawlerTaskRun.max_attempts,
        ).order_by(CrawlerTaskRun.run_id).limit(100)).all()
        for run in rows:
            if db.scalar(select(exists().where(CrawlerTaskRun.parent_run_id == run.run_id))):
                continue
            schedule = db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == run.task_id))
            if not schedule:
                continue
            multiplier = 2 ** max(0, run.attempt - 1) if schedule.retry_backoff == "EXPONENTIAL" else 1
            due = run.finished_at + timedelta(seconds=schedule.retry_interval_seconds * multiplier)
            if due > now:
                continue
            task = db.scalar(select(CrawlerTask).options(
                selectinload(CrawlerTask.runtime),
                selectinload(CrawlerTask.schedule),
                selectinload(CrawlerTask.targets),
            ).where(CrawlerTask.task_id == run.task_id))
            if not task:
                continue
            try:
                create_retry(db, run, scheduled_at=due)
            except RunCreationError as exc:
                print(f"Create retry failed run={run.run_id}: {exc}", flush=True)

    def recover_expired_runs(self, db: Session) -> None:
        now = utcnow()
        rows = db.scalars(select(CrawlerTaskRun).where(
            CrawlerTaskRun.status.in_(ACTIVE_STATUSES),
            CrawlerTaskRun.lease_expires_at.is_not(None),
            CrawlerTaskRun.lease_expires_at < now,
        )).all()
        for run in rows:
            try:
                transition(run, "LOST")
            except Exception:
                run.status = "LOST"
                run.finished_at = now
            run.terminal_error_code = "AGENT.LEASE_EXPIRED"
            run.terminal_error_type = "AgentLeaseExpiredError"
            run.terminal_error_message = "Agent 运行租约过期，原运行已标记为 LOST"
            run.error_type = run.terminal_error_type
            run.error_message = run.terminal_error_message
            run.lease_expires_at = None

        active = db.scalars(select(CrawlerTaskRun).where(
            CrawlerTaskRun.status.in_(["STARTING", "RUNNING"]),
            CrawlerTaskRun.started_at.is_not(None),
        )).all()
        for run in active:
            timeout = int((run.task_spec_json or {}).get("timeout_seconds", 0))
            if timeout > 0 and run.started_at + timedelta(seconds=timeout) < now:
                if run.status != "CANCEL_REQUESTED":
                    try:
                        transition(run, "CANCEL_REQUESTED")
                    except Exception:
                        pass
                run.desired_action = "TIMEOUT_STOP"

    def mark_offline_agents(self, db: Session) -> None:
        threshold = utcnow() - timedelta(seconds=settings.agent_offline_seconds)
        agents = db.scalars(select(CrawlerAgent).where(CrawlerAgent.last_heartbeat_at < threshold)).all()
        for agent in agents:
            agent.status = "OFFLINE"
            server = db.get(CrawlerServer, agent.server_id)
            if server and server.status != "DISABLED":
                server.status = "OFFLINE"
