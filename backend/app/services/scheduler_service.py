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
from app.services.run_service import RunCreationError, create_run
from app.utils import utcnow


class SchedulerService:
    def __init__(self) -> None:
        self.lock_name = "crawler:scheduler:leader"
        self.token = str(uuid.uuid4())
        self.redis = self._create_redis_client()

    @staticmethod
    def _create_redis_client() -> redis.Redis:
        return redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
            retry_on_timeout=True,
        )

    def _reset_redis_client(self) -> None:
        try:
            self.redis.close()
        except Exception:
            pass
        self.redis = self._create_redis_client()

    def acquire_lock(self) -> bool:
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                return bool(self.redis.set(self.lock_name, self.token, nx=True, ex=settings.scheduler_lock_seconds))
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as exc:
                last_error = exc
                self._reset_redis_client()
                if attempt < 5:
                    time.sleep(min(attempt, 3))
        if last_error:
            raise last_error
        return False

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
        print("Scheduler started")
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
                print(f"Scheduler error: {exc!r}")
            time.sleep(settings.scheduler_poll_seconds)

    def initialize_schedules(self, db: Session) -> None:
        rows = db.scalars(
            select(CrawlerTaskSchedule).where(
                CrawlerTaskSchedule.enabled.is_(True),
                CrawlerTaskSchedule.schedule_type == "CRON",
                CrawlerTaskSchedule.next_run_at.is_(None),
            )
        ).all()
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
            .options(selectinload(CrawlerTaskSchedule.task).selectinload(CrawlerTask.runtime), selectinload(CrawlerTaskSchedule.task).selectinload(CrawlerTask.targets))
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
            is_late = scheduled_at < now - timedelta(seconds=max(settings.scheduler_poll_seconds * 2, 15))
            should_create = not is_late or schedule.misfire_policy in {"FIRE_NOW", "FIRE_ONCE"}
            if should_create:
                try:
                    with db.begin_nested():
                        create_run(db, schedule.task, "SCHEDULE", scheduled_at=scheduled_at, schedule=schedule)
                        db.flush()
                except (RunCreationError, IntegrityError) as exc:
                    print(f"Create scheduled run failed task={schedule.task_id}: {exc}")
            schedule.last_triggered_at = now
            schedule.next_run_at = next_run_utc(schedule.cron_expression, schedule.timezone, now)
            db.flush()

    def dispatch_retries(self, db: Session) -> None:
        now = utcnow()
        failed_runs = db.scalars(
            select(CrawlerTaskRun)
            .where(CrawlerTaskRun.status.in_(["FAILED", "TIMEOUT", "LOST"]), CrawlerTaskRun.finished_at.is_not(None))
            .order_by(CrawlerTaskRun.run_id.asc())
            .limit(100)
        ).all()
        for run in failed_runs:
            schedule = db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == run.task_id))
            if not schedule or run.attempt > schedule.max_retry_count:
                continue
            child_exists = db.scalar(select(exists().where(CrawlerTaskRun.parent_run_id == run.run_id)))
            if child_exists:
                continue
            multiplier = 2 ** max(0, run.attempt - 1) if schedule.retry_backoff == "EXPONENTIAL" else 1
            due_at = run.finished_at + timedelta(seconds=schedule.retry_interval_seconds * multiplier)
            if due_at > now:
                continue
            task = db.scalar(
                select(CrawlerTask)
                .options(selectinload(CrawlerTask.runtime), selectinload(CrawlerTask.schedule), selectinload(CrawlerTask.targets))
                .where(CrawlerTask.task_id == run.task_id)
            )
            if not task:
                continue
            try:
                create_run(
                    db,
                    task,
                    "RETRY",
                    scheduled_at=due_at,
                    schedule=schedule,
                    attempt=run.attempt + 1,
                    parent_run_id=run.run_id,
                )
            except RunCreationError as exc:
                print(f"Create retry failed run={run.run_id}: {exc}")

    def recover_expired_runs(self, db: Session) -> None:
        now = utcnow()
        rows = db.scalars(
            select(CrawlerTaskRun).where(
                CrawlerTaskRun.status.in_(["CLAIMED", "STARTING", "RUNNING"]),
                CrawlerTaskRun.lease_expires_at.is_not(None),
                CrawlerTaskRun.lease_expires_at < now,
            )
        ).all()
        for run in rows:
            if run.status in {"CLAIMED", "STARTING"} and not run.container_id:
                run.status = "QUEUED"
                run.agent_id = None
                run.claimed_at = None
                run.heartbeat_at = None
                run.lease_expires_at = None
            else:
                run.status = "LOST"
                run.finished_at = now
                run.error_type = "AGENT_LEASE_EXPIRED"
                run.error_message = "Agent 心跳租约过期，任务状态已标记为 LOST"
                run.lease_expires_at = None
                if run.started_at:
                    run.duration_ms = int((now - run.started_at).total_seconds() * 1000)

        active = db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.status == "RUNNING", CrawlerTaskRun.started_at.is_not(None))).all()
        for run in active:
            schedule = db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == run.task_id))
            if schedule and run.started_at + timedelta(seconds=schedule.timeout_seconds) < now:
                run.desired_action = "TIMEOUT_STOP"

    def mark_offline_agents(self, db: Session) -> None:
        threshold = utcnow() - timedelta(seconds=90)
        agents = db.scalars(select(CrawlerAgent).where(CrawlerAgent.last_heartbeat_at < threshold)).all()
        for agent in agents:
            agent.status = "OFFLINE"
            server = db.get(CrawlerServer, agent.server_id)
            if server and server.status != "DISABLED":
                server.status = "OFFLINE"
