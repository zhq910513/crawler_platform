from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerReleaseChannel, CrawlerTask, CrawlerTaskRun, CrawlerTaskSchedule, SysAlertEvent, SysUser
from app.repositories.platform import RunRepository, TaskRepository
from app.schemas import ManualRunCreate
from app.services.permissions import is_super_admin, require_project_role, scoped_company_id
from app.services.routing_service import RoutingService
from app.services.state_machine import RUN_TERMINAL, safe_set_run_status, set_routing_status, set_synthetic_parent_terminal
from app.utils import utcnow

AUTO_RETRY_STATUSES = {"FAILED", "TIMED_OUT", "LOST"}
AUTO_RETRY_POLICIES = {"IDEMPOTENT", "CHECKPOINTABLE"}
ACTIVE_RUN_STATUSES = {"QUEUED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}


class RunService:
    def __init__(self, db: Session):
        self.db = db
        self.runs = RunRepository(db)
        self.tasks = TaskRepository(db)
        self.router = RoutingService(db)

    def list_runs(self, user: SysUser, company_id: int | None = None, project_id: int | None = None, task_id: int | None = None) -> list[CrawlerTaskRun]:
        if is_super_admin(user):
            return self.runs.list_runs(company_id=company_id, project_id=project_id, task_id=task_id)
        scoped = scoped_company_id(user, company_id)
        return self.runs.list_runs(company_id=scoped, project_id=project_id, task_id=task_id, user_id=user.user_id)

    def create_manual_run(self, user: SysUser, payload: ManualRunCreate) -> CrawlerTaskRun:
        task = self.tasks.get(payload.task_id)
        if not task:
            raise AppError("任务不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, user, task.project_id, "OPERATOR")
        run = self.create_run(task, None, utcnow(), payload.parameters, trigger_type="MANUAL")
        self.db.commit()
        return run

    def create_run(
        self,
        task: CrawlerTask,
        schedule: CrawlerTaskSchedule | None,
        scheduled_at: datetime,
        parameters: dict[str, Any] | None = None,
        trigger_type: str = "SCHEDULE",
        hold_for_queue: bool = False,
    ) -> CrawlerTaskRun:
        if task.status not in {"ENABLED", "DRAFT"} and trigger_type == "MANUAL":
            raise AppError("任务状态不允许手动执行", code=40061)
        if task.status != "ENABLED" and trigger_type != "MANUAL":
            raise AppError("任务未启用", code=40062)
        release = self._resolve_release(task)
        if not release:
            raise AppError("任务未绑定可用发布版本", code=40064)
        if task.execution_mode == "SHARDED":
            return self._create_sharded_run(task, schedule, scheduled_at, parameters or {}, release, trigger_type, hold_for_queue)
        return self._create_single_run(task, schedule, scheduled_at, parameters or {}, release, trigger_type, None, None, hold_for_queue, "single")

    def request_cancel(self, user: SysUser, run_id: int) -> CrawlerTaskRun:
        run = self.runs.get(run_id)
        if not run:
            raise AppError("运行实例不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, user, run.project_id, "OPERATOR")
        if run.run_status in RUN_TERMINAL:
            raise AppError("终态运行实例不可取消", code=40063)
        if run.run_status in {"ASSIGNED", "STARTING", "RUNNING"}:
            safe_set_run_status(run, "CANCEL_REQUESTED")
        else:
            safe_set_run_status(run, "CANCELLED")
            run.finished_at = utcnow()
            set_routing_status(run, "ROUTE_CANCELLED", reason="用户取消运行")
        self.db.commit()
        return run

    def mark_lost_runs(self) -> int:
        expired_runs = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.run_status.in_(["ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"]), CrawlerTaskRun.lease_expires_at.is_not(None), CrawlerTaskRun.lease_expires_at < utcnow()).limit(300)).all())
        for run in expired_runs:
            safe_set_run_status(run, "LOST", message="Agent 租约过期，运行状态已标记为失联")
            run.finished_at = utcnow()
            run.lease_expires_at = None
            self.maybe_retry(run)
            self.aggregate_sharded_parent(run.parent_run_id)
        if len(expired_runs) >= 10:
            self._raise_p0_alert("大量运行实例失联", f"本轮检测到 {len(expired_runs)} 个运行实例进入 LOST。", "run_lost_massive")
        self.db.commit()
        return len(expired_runs)

    def maybe_retry(self, run: CrawlerTaskRun) -> CrawlerTaskRun | None:
        if run.run_status not in AUTO_RETRY_STATUSES:
            return None
        task = self.db.get(CrawlerTask, run.task_id)
        if not task:
            return None
        if task.idempotency_policy not in AUTO_RETRY_POLICIES:
            if task.idempotency_policy in {"MANUAL_CONFIRM", "NON_IDEMPOTENT"}:
                self._raise_p0_alert("非幂等任务需要人工处理", f"运行实例 {run.run_id} 进入 {run.run_status}，该任务禁止自动重跑。", f"non_idempotent_run_{run.run_id}", run.company_id, run.project_id)
            return None
        if run.attempt >= run.max_attempts:
            return None
        release = self.db.get(__import__("app.models", fromlist=["CrawlerProjectRelease"]).CrawlerProjectRelease, run.release_id) if run.release_id else self._resolve_release(task)
        if not release:
            return None
        retry = self._create_single_run(task, None, utcnow(), dict(run.parameters_snapshot or {}), release, run.trigger_type, run.shard_index, run.shard_count, False, f"retry:{run.run_id}:{run.attempt + 1}")
        retry.attempt = run.attempt + 1
        retry.max_attempts = run.max_attempts
        retry.root_run_id = run.root_run_id or run.run_id
        retry.parent_run_id = run.parent_run_id
        retry.retry_reason = f"由运行实例 {run.run_id} 的 {run.run_status} 自动重试创建"
        return retry

    def aggregate_sharded_parent(self, parent_run_id: int | None) -> CrawlerTaskRun | None:
        if not parent_run_id:
            return None
        parent = self.db.get(CrawlerTaskRun, parent_run_id)
        if not parent or parent.run_status in RUN_TERMINAL:
            return parent
        children = list(self.db.scalars(select(CrawlerTaskRun).where(CrawlerTaskRun.parent_run_id == parent_run_id)).all())
        if not children or any(child.run_status not in RUN_TERMINAL for child in children):
            return parent
        statuses = {child.run_status for child in children}
        if statuses <= {"SUCCEEDED", "SKIPPED"} and "SUCCEEDED" in statuses:
            set_synthetic_parent_terminal(parent, "SUCCEEDED")
        elif "SUCCEEDED" in statuses or "PARTIAL_SUCCESS" in statuses:
            set_synthetic_parent_terminal(parent, "PARTIAL_SUCCESS", message="分片任务部分成功，请检查失败分片")
        elif "CANCELLED" in statuses and statuses <= {"CANCELLED", "SKIPPED"}:
            set_synthetic_parent_terminal(parent, "CANCELLED")
        elif "TIMED_OUT" in statuses:
            set_synthetic_parent_terminal(parent, "TIMED_OUT", message="至少一个分片超时")
        elif "LOST" in statuses:
            set_synthetic_parent_terminal(parent, "LOST", message="至少一个分片失联")
        else:
            set_synthetic_parent_terminal(parent, "FAILED", message="分片任务失败")
        parent.finished_at = utcnow()
        self.db.flush()
        return parent

    def _resolve_release(self, task: CrawlerTask):
        if task.image_policy == "PINNED" and task.fixed_release_id:
            return self.db.get(__import__("app.models", fromlist=["CrawlerProjectRelease"]).CrawlerProjectRelease, task.fixed_release_id)
        channel = self.db.scalar(select(CrawlerReleaseChannel).where(CrawlerReleaseChannel.project_id == task.project_id, CrawlerReleaseChannel.channel_name == task.release_channel, CrawlerReleaseChannel.channel_status == "ENABLED"))
        return self.db.get(__import__("app.models", fromlist=["CrawlerProjectRelease"]).CrawlerProjectRelease, channel.release_id) if channel and channel.release_id else None

    @staticmethod
    def _trigger_key(schedule: CrawlerTaskSchedule | None, scheduled_at: datetime, trigger_type: str, suffix: str) -> str | None:
        if not schedule:
            return None
        return f"schedule:{schedule.schedule_id}:{scheduled_at.isoformat()}:{suffix}"

    def _create_single_run(self, task: CrawlerTask, schedule: CrawlerTaskSchedule | None, scheduled_at: datetime, parameters: dict[str, Any], release, trigger_type: str, shard_index: int | None, shard_count: int | None, hold_for_queue: bool, trigger_suffix: str) -> CrawlerTaskRun:
        run = CrawlerTaskRun(company_id=task.company_id, project_id=task.project_id, task_id=task.task_id, schedule_id=schedule.schedule_id if schedule else None, release_id=release.release_id, image_repository=release.image_repository, image_digest=release.image_digest, entry_module=task.entry_module, entry_function=task.entry_function, execution_mode=task.execution_mode, shard_index=shard_index, shard_count=shard_count, trigger_type=trigger_type, idempotency_policy=task.idempotency_policy, cpu_limit=task.cpu_limit, memory_limit_mb=task.memory_limit_mb, timeout_seconds=task.timeout_seconds, runtime_mode=task.runtime_mode, task_group=task.task_group, task_max_concurrency=task.task_max_concurrency, group_max_concurrency=task.group_max_concurrency, exclusive_mode=task.exclusive_mode, io_class=task.io_class, shm_size_mb=task.shm_size_mb, log_limit_mb=task.log_limit_mb, resource_locks=task.resource_locks or [], run_status="QUEUED", routing_status="PENDING", scheduled_at=scheduled_at, trigger_key=self._trigger_key(schedule, scheduled_at, trigger_type, trigger_suffix), attempt=1, max_attempts=max(1, task.max_retry_count + 1), parameters_snapshot={**(task.parameters or {}), **parameters})
        self.db.add(run)
        self.db.flush()
        run.root_run_id = run.run_id
        if hold_for_queue:
            set_routing_status(run, "WAITING_RESOURCE", reason="重叠策略排队等待上一轮结束")
        else:
            self.router.route_run(run)
        return run

    def _create_sharded_run(self, task: CrawlerTask, schedule: CrawlerTaskSchedule | None, scheduled_at: datetime, parameters: dict[str, Any], release, trigger_type: str, hold_for_queue: bool) -> CrawlerTaskRun:
        shard_count = max(1, min(task.max_parallel_nodes, task.required_node_count))
        parent = CrawlerTaskRun(company_id=task.company_id, project_id=task.project_id, task_id=task.task_id, schedule_id=schedule.schedule_id if schedule else None, release_id=release.release_id, image_repository=release.image_repository, image_digest=release.image_digest, entry_module=task.entry_module, entry_function=task.entry_function, execution_mode="SHARDED", shard_count=shard_count, trigger_type=trigger_type, idempotency_policy=task.idempotency_policy, cpu_limit=task.cpu_limit, memory_limit_mb=task.memory_limit_mb, timeout_seconds=task.timeout_seconds, runtime_mode=task.runtime_mode, task_group=task.task_group, task_max_concurrency=task.task_max_concurrency, group_max_concurrency=task.group_max_concurrency, exclusive_mode=task.exclusive_mode, io_class=task.io_class, shm_size_mb=task.shm_size_mb, log_limit_mb=task.log_limit_mb, resource_locks=task.resource_locks or [], run_status="RUNNING", routing_status="ROUTE_CANCELLED", routing_reason="父运行实例，用于聚合分片状态", scheduled_at=scheduled_at, trigger_key=self._trigger_key(schedule, scheduled_at, trigger_type, "parent"), started_at=utcnow(), attempt=1, max_attempts=max(1, task.max_retry_count + 1), parameters_snapshot={**(task.parameters or {}), **parameters})
        self.db.add(parent)
        self.db.flush()
        parent.root_run_id = parent.run_id
        for index in range(shard_count):
            child_params = {**parameters, "shardIndex": index, "shardCount": shard_count}
            child = self._create_single_run(task, schedule, scheduled_at, child_params, release, trigger_type, index, shard_count, hold_for_queue, f"shard:{index}")
            child.parent_run_id = parent.run_id
            child.root_run_id = parent.run_id
        return parent

    def _raise_p0_alert(self, title: str, content: str, fingerprint: str, company_id: int | None = None, project_id: int | None = None) -> None:
        existing = self.db.scalar(select(SysAlertEvent).where(SysAlertEvent.fingerprint == fingerprint, SysAlertEvent.alert_status.in_(["OPEN", "NOTIFYING", "NOTIFIED", "ACKED"])))
        if existing:
            existing.occurrence_count += 1
            existing.last_seen_at = utcnow()
            return
        self.db.add(SysAlertEvent(company_id=company_id, project_id=project_id, severity="P0", alert_status="OPEN", alert_type="RUNTIME", title=title, content=content, fingerprint=fingerprint, notify_after_at=utcnow()))
