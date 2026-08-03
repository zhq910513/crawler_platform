from __future__ import annotations

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerProjectServer, CrawlerProjectTaskDefinition, CrawlerTask, CrawlerTaskSchedule, CrawlerTaskServerTarget, SysUser
from app.repositories.platform import ProjectRepository, TaskDefinitionRepository, TaskRepository
from app.schemas import ScheduleUpdate, TaskFromDefinitionCreate, TaskUpdate
from app.services.audit import write_operation_log
from app.services.cron_service import CronService
from app.services.permissions import is_super_admin, require_project_role, scoped_company_id


class TaskService:
    def __init__(self, db: Session):
        self.db = db
        self.tasks = TaskRepository(db)
        self.definitions = TaskDefinitionRepository(db)
        self.projects = ProjectRepository(db)

    def list_definitions(self, user: SysUser, project_id: int) -> list[CrawlerProjectTaskDefinition]:
        require_project_role(self.db, user, project_id, "VIEWER")
        return self.definitions.list_by_project(project_id)

    def list_tasks(self, user: SysUser, company_id: int | None = None, project_id: int | None = None) -> list[dict]:
        if project_id:
            require_project_role(self.db, user, project_id, "VIEWER")
            rows = self.tasks.list_tasks(project_id=project_id)
        elif is_super_admin(user):
            rows = self.tasks.list_tasks(company_id=company_id)
        else:
            scoped = scoped_company_id(user, company_id)
            rows = self.tasks.list_tasks(company_id=scoped, user_id=user.user_id)
        return [self._task_payload(row) for row in rows]

    def _prepare_schedule_fields(self, schedule_type: str, cron_expression: str, schedule_config: dict | None, timezone: str, current_user: SysUser) -> tuple[str, dict, str]:
        if schedule_type != "CRON":
            return "", schedule_config or {}, "手动执行"
        config = schedule_config or {}
        if config.get("mode"):
            expr, normalized, label = CronService.normalize_config(config, timezone)
            if expr:
                expr = CronService.validate(expr, timezone, is_super_admin=is_super_admin(current_user))
                return expr, normalized, label
        expr = CronService.validate(cron_expression, timezone, is_super_admin=is_super_admin(current_user))
        return expr, config, CronService.label_from_config(config, expr)

    def create_from_definition(self, user: SysUser, payload: TaskFromDefinitionCreate) -> CrawlerTask:
        definition = self.definitions.get(payload.definition_id)
        if not definition:
            raise AppError("任务定义不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        project = require_project_role(self.db, user, definition.project_id, "OPERATOR")
        if definition.definition_status == "CREATED":
            raise AppError("该任务定义已经创建正式任务", code=40051)
        task = CrawlerTask(
            company_id=project.company_id,
            project_id=project.project_id,
            definition_id=definition.definition_id,
            task_code=payload.task_code,
            task_name=payload.task_name,
            entry_module=definition.entry_module,
            entry_function=definition.entry_function,
            parameters=payload.parameters or definition.default_params,
            execution_mode=definition.execution_mode,
            shard_strategy=definition.resource_requirements.get("shardStrategy", {}) if isinstance(definition.resource_requirements, dict) else {},
            required_node_count=max(1, int((definition.resource_requirements or {}).get("requiredNodeCount", 1))) if definition.execution_mode == "SHARDED" else 1,
            max_parallel_nodes=max(1, int((definition.resource_requirements or {}).get("maxParallelNodes", 1))) if definition.execution_mode == "SHARDED" else 1,
            required_capabilities=definition.required_capabilities or {},
            runtime_mode=payload.runtime_mode or definition.runtime_mode or project.default_runtime_mode,
            task_group=payload.task_group or definition.task_group or "default",
            task_max_concurrency=payload.task_max_concurrency or definition.task_max_concurrency or project.default_task_max_concurrency,
            group_max_concurrency=payload.group_max_concurrency or definition.group_max_concurrency or project.default_group_max_concurrency,
            exclusive_mode=definition.exclusive_mode if payload.exclusive_mode is None else payload.exclusive_mode,
            io_class=payload.io_class or definition.io_class or "NORMAL",
            shm_size_mb=payload.shm_size_mb or definition.shm_size_mb or project.default_shm_size_mb,
            log_limit_mb=payload.log_limit_mb or definition.log_limit_mb or project.default_log_limit_mb,
            resource_locks=payload.resource_locks if payload.resource_locks is not None else (definition.resource_locks or []),
            idempotency_policy=definition.idempotency_policy,
            status=payload.status,
            image_policy=payload.image_policy,
            release_channel=payload.release_channel,
            fixed_release_id=payload.fixed_release_id,
            cpu_limit=float(payload.cpu_limit),
            memory_limit_mb=payload.memory_limit_mb,
            timeout_seconds=payload.timeout_seconds,
            max_retry_count=payload.max_retry_count,
            description=payload.description,
        )
        self.db.add(task)
        self.db.flush()
        next_run_at = None
        cron_expression, schedule_config, schedule_label = self._prepare_schedule_fields(payload.schedule_type, payload.cron_expression, payload.schedule_config, payload.schedule_timezone, user)
        if payload.schedule_status == "ENABLED" and payload.schedule_type == "CRON":
            next_run_at = CronService.next_time(cron_expression, payload.schedule_timezone, is_super_admin=is_super_admin(user))
        schedule = CrawlerTaskSchedule(
            company_id=project.company_id,
            project_id=project.project_id,
            task_id=task.task_id,
            schedule_status=payload.schedule_status,
            schedule_type=payload.schedule_type,
            cron_expression=cron_expression,
            schedule_timezone=payload.schedule_timezone,
            overlap_policy=payload.overlap_policy,
            schedule_config=schedule_config,
            schedule_label=payload.schedule_label or schedule_label,
            next_run_at=next_run_at,
        )
        self.db.add(schedule)
        for server_id in payload.server_ids:
            ps = self.db.scalar(select(CrawlerProjectServer).where(CrawlerProjectServer.project_id == project.project_id, CrawlerProjectServer.server_id == server_id, CrawlerProjectServer.deployment_status == "DEPLOYED"))
            if not ps:
                raise AppError("任务指定服务器必须属于该项目已部署服务器", code=40053)
            self.db.add(CrawlerTaskServerTarget(company_id=project.company_id, task_id=task.task_id, server_id=server_id))
        definition.definition_status = "CREATED"
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise AppError("任务编码或任务定义已存在", code=40052) from exc
        return task

    def update_task(self, user: SysUser, task_id: int, payload: TaskUpdate) -> CrawlerTask:
        task = self.tasks.get(task_id)
        if not task:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, user, task.project_id, "OPERATOR")
        before = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(task, key, value)
        after = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_TASK", resource_type="task", resource_id=str(task.task_id), before_data=before, after_data=after)
        self.db.commit()
        return task

    def update_schedule(self, user: SysUser, task_id: int, payload: ScheduleUpdate) -> CrawlerTaskSchedule:
        task = self.tasks.get(task_id)
        if not task:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, user, task.project_id, "OPERATOR")
        schedule = self.db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == task_id))
        if not schedule:
            schedule = CrawlerTaskSchedule(company_id=task.company_id, project_id=task.project_id, task_id=task_id)
            self.db.add(schedule)
            self.db.flush()
        before = {c.name: getattr(schedule, c.name) for c in schedule.__table__.columns}
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(schedule, key, value)
        if schedule.schedule_type == "CRON":
            schedule.cron_expression, schedule.schedule_config, generated_label = self._prepare_schedule_fields(schedule.schedule_type, schedule.cron_expression, schedule.schedule_config, schedule.schedule_timezone, user)
            schedule.schedule_label = schedule.schedule_label or generated_label
        else:
            schedule.next_run_at = None
            schedule.cron_expression = ""
            schedule.schedule_label = schedule.schedule_label or "手动执行"
        if schedule.schedule_status == "ENABLED" and schedule.schedule_type == "CRON" and schedule.cron_expression:
            schedule.next_run_at = CronService.next_time(schedule.cron_expression, schedule.schedule_timezone, is_super_admin=is_super_admin(user))
        elif schedule.schedule_status != "ENABLED":
            schedule.next_run_at = None
        after = {c.name: getattr(schedule, c.name) for c in schedule.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_SCHEDULE", resource_type="task_schedule", resource_id=str(schedule.schedule_id), before_data=before, after_data=after)
        self.db.commit()
        return schedule

    def _task_payload(self, task: CrawlerTask) -> dict:
        schedule = self.db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == task.task_id))
        data = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        if schedule:
            data.update({
                "schedule_id": schedule.schedule_id,
                "schedule_status": schedule.schedule_status,
                "schedule_type": schedule.schedule_type,
                "cron_expression": schedule.cron_expression,
                "schedule_timezone": schedule.schedule_timezone,
                "overlap_policy": schedule.overlap_policy,
                "schedule_config": schedule.schedule_config,
                "schedule_label": schedule.schedule_label,
                "next_run_at": schedule.next_run_at,
                "last_triggered_at": schedule.last_triggered_at,
            })
        return data
