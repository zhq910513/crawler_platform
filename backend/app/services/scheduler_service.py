from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerProject, CrawlerTask, CrawlerTaskRun, CrawlerTaskSchedule
from app.services.cron_service import CronService
from app.services.run_service import ACTIVE_RUN_STATUSES, RunService, build_runtime_parameters
from app.services.state_machine import safe_set_run_status, set_routing_status
from app.utils import utcnow


class SchedulerService:
    def __init__(self, db: Session):
        self.db = db
        self.run_service = RunService(db)

    def dispatch_due_schedules(self, limit: int = 100) -> int:
        due_ids = list(
            self.db.scalars(
                select(CrawlerTaskSchedule.schedule_id)
                .where(
                    CrawlerTaskSchedule.schedule_status == "ENABLED",
                    CrawlerTaskSchedule.schedule_type == "CRON",
                    CrawlerTaskSchedule.next_run_at.is_not(None),
                    CrawlerTaskSchedule.next_run_at <= utcnow(),
                )
                .order_by(CrawlerTaskSchedule.next_run_at.asc())
                .limit(limit)
            ).all()
        )
        created = 0
        for schedule_id in due_ids:
            schedule = self.db.get(CrawlerTaskSchedule, schedule_id)
            if not schedule or schedule.schedule_status != "ENABLED" or schedule.schedule_type != "CRON" or not schedule.next_run_at or schedule.next_run_at > utcnow():
                continue
            task = self.db.get(CrawlerTask, schedule.task_id)
            project = self.db.get(CrawlerProject, schedule.project_id)
            scheduled_at = schedule.next_run_at or utcnow()
            try:
                if not task or not project or task.status != "ENABLED" or project.status != "ENABLED" or project.online_status != "ONLINE":
                    self._create_skipped(task, schedule, scheduled_at, "项目或任务状态不允许调度")
                    self._advance(schedule, scheduled_at)
                    self.db.commit()
                    continue
                active_runs = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task.task_id, CrawlerTaskRun.run_status.in_(list(ACTIVE_RUN_STATUSES)))).all())
                if active_runs and schedule.overlap_policy == "SKIP":
                    self._create_skipped(task, schedule, scheduled_at, "重叠策略跳过")
                else:
                    hold_for_queue = bool(active_runs and schedule.overlap_policy == "QUEUE")
                    if active_runs and schedule.overlap_policy == "CANCEL_OLD":
                        for run in active_runs:
                            if run.run_status == "QUEUED":
                                safe_set_run_status(run, "CANCELLED", message="新调度触发，取消旧运行")
                                run.finished_at = utcnow()
                                if run.routing_status != "ROUTE_CANCELLED":
                                    set_routing_status(run, "ROUTE_CANCELLED", reason="新调度触发，取消旧运行")
                            elif run.run_status in {"ASSIGNED", "STARTING", "RUNNING"}:
                                safe_set_run_status(run, "CANCEL_REQUESTED", message="新调度触发，请求取消旧运行")
                    self.run_service.create_run(task, schedule, scheduled_at, {}, trigger_type="SCHEDULE", hold_for_queue=hold_for_queue)
                    created += 1
                self._advance(schedule, scheduled_at)
                self.db.commit()
            except IntegrityError:
                self.db.rollback()
                self._advance_after_duplicate(schedule_id, scheduled_at)
                continue
            except AppError as exc:
                self.db.rollback()
                schedule = self.db.get(CrawlerTaskSchedule, schedule_id)
                task = self.db.get(CrawlerTask, schedule.task_id) if schedule else None
                if schedule:
                    self._create_skipped(task, schedule, scheduled_at, exc.message)
                    self._advance(schedule, scheduled_at)
                    try:
                        self.db.commit()
                    except IntegrityError:
                        self.db.rollback()
                        self._advance_after_duplicate(schedule_id, scheduled_at)
        return created

    def _advance_after_duplicate(self, schedule_id: int, scheduled_at) -> None:
        schedule = self.db.get(CrawlerTaskSchedule, schedule_id)
        if not schedule:
            return
        if schedule.next_run_at and schedule.next_run_at <= scheduled_at:
            self._advance(schedule, scheduled_at)
            self.db.commit()

    def _create_skipped(self, task: CrawlerTask | None, schedule: CrawlerTaskSchedule, scheduled_at, reason: str) -> None:
        if not task:
            return
        self.db.add(CrawlerTaskRun(company_id=task.company_id, project_id=task.project_id, task_id=task.task_id, schedule_id=schedule.schedule_id, scheduled_at=scheduled_at, trigger_key=f"schedule:{schedule.schedule_id}:{scheduled_at.isoformat()}:skipped", run_status="SKIPPED", routing_status="ROUTE_CANCELLED", routing_reason=reason, trigger_type="SCHEDULE", entry_module=task.entry_module, entry_function=task.entry_function, execution_mode=task.execution_mode, idempotency_policy=task.idempotency_policy, parameters_snapshot=build_runtime_parameters(task, {})))

    def _advance(self, schedule: CrawlerTaskSchedule, scheduled_at) -> None:
        schedule.last_triggered_at = scheduled_at
        schedule.next_run_at = self.next_time(schedule)

    @staticmethod
    def next_time(schedule: CrawlerTaskSchedule):
        return CronService.next_time(schedule.cron_expression, schedule.schedule_timezone, is_super_admin=True)
