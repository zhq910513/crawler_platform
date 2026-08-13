from __future__ import annotations

from typing import Any

from fastapi import status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerProjectRelease, CrawlerProjectServer, CrawlerProjectTaskDefinition, CrawlerTask, CrawlerTaskRun, CrawlerTaskSchedule, CrawlerTaskServerTarget, SysUser
from app.repositories.platform import ProjectRepository, TaskDefinitionRepository, TaskRepository
from app.schemas import ScheduleUpdate, TaskFromDefinitionCreate, TaskUpdate
from app.services.audit import write_operation_log
from app.services.cron_service import CronService
from app.services.container_cleanup_service import ContainerCleanupService
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
            rows = self.tasks.list_tasks(company_id=scoped)
        return [self._task_payload(row) for row in rows]

    def _binding_value_exists(self, value: Any) -> bool:
        return value is not None and value != "" and value != {} and value != []

    def _credential_mode(self, binding: Any) -> str:
        if isinstance(binding, str):
            return "fixed"
        if isinstance(binding, list):
            return "fixed_list"
        if isinstance(binding, dict):
            return str(binding.get("mode") or "fixed").strip()
        return ""

    def _validate_credential_binding(self, slot: str, requirement: dict[str, Any], binding: Any) -> list[str]:
        errors: list[str] = []
        if not isinstance(requirement, dict):
            return errors
        required = bool(requirement.get("required", False))
        if not self._binding_value_exists(binding):
            if required:
                errors.append(f"账号绑定项 {slot} 必须配置")
            return errors
        mode = self._credential_mode(binding)
        allowed = set(str(item) for item in (requirement.get("supportedModes") or requirement.get("supported_modes") or ["fixed"]))
        if mode not in allowed:
            errors.append(f"账号绑定项 {slot} 不支持模式 {mode}，允许：{sorted(allowed)}")
        expected_platform = str(requirement.get("platformCode") or requirement.get("platform_code") or "").strip().lower()
        expected_type = str(requirement.get("credentialType") or requirement.get("credential_type") or "").strip()
        if isinstance(binding, dict):
            actual_platform = str(binding.get("platformCode") or binding.get("platform_code") or "").strip().lower()
            actual_type = str(binding.get("credentialType") or binding.get("credential_type") or "").strip()
            if expected_platform and actual_platform and actual_platform != expected_platform:
                errors.append(f"账号绑定项 {slot} platformCode 不匹配：期望 {expected_platform}，实际 {actual_platform}")
            if expected_type and actual_type and actual_type != expected_type:
                errors.append(f"账号绑定项 {slot} credentialType 不匹配：期望 {expected_type}，实际 {actual_type}")
            if mode == "fixed":
                if not (binding.get("credentialKey") or binding.get("credential_key") or binding.get("credentialRef") or binding.get("credential_ref") or isinstance(binding.get("credential"), dict)):
                    errors.append(f"账号绑定项 {slot} fixed 模式必须配置 credentialKey/credentialRef")
            elif mode == "fixed_list":
                keys = binding.get("credentialKeys") or binding.get("credential_keys") or binding.get("credentialRefs") or binding.get("credential_refs") or binding.get("credentials")
                if not isinstance(keys, list) or not keys:
                    errors.append(f"账号绑定项 {slot} fixed_list 模式必须配置非空账号列表")
            elif mode == "pool":
                if not (binding.get("selector") or actual_platform or expected_platform):
                    errors.append(f"账号绑定项 {slot} pool 模式必须配置 selector 或 platformCode")
            elif mode == "binding_rule":
                rules = binding.get("rules") or []
                if not isinstance(rules, list) or not rules:
                    errors.append(f"账号绑定项 {slot} binding_rule 模式必须配置 rules")
            elif mode in {"affinity_pool", "external_affinity_pool"}:
                subject_type = binding.get("subjectType") or binding.get("subject_type") or (requirement.get("affinity") or {}).get("subjectType") or (requirement.get("affinity") or {}).get("subject_type")
                if not subject_type:
                    errors.append(f"账号绑定项 {slot} {mode} 模式必须配置 subjectType")
                if mode == "external_affinity_pool" and not (binding.get("externalField") or binding.get("external_field") or binding.get("externalSubjectField") or binding.get("external_subject_field")):
                    errors.append(f"账号绑定项 {slot} external_affinity_pool 模式必须配置 externalField")
        elif mode == "fixed_list" and not binding:
            errors.append(f"账号绑定项 {slot} fixed_list 模式账号列表不能为空")
        elif mode == "fixed" and isinstance(binding, str) and not binding.strip():
            errors.append(f"账号绑定项 {slot} fixed 模式账号不能为空")
        return errors

    def _validate_task_contract_bindings(self, *, required_configs: list[Any] | None, required_credentials: list[Any] | None, config_bindings: dict[str, Any] | None, credential_bindings: dict[str, Any] | None, target_status: str = "DRAFT") -> None:
        errors: list[str] = []
        configs = config_bindings or {}
        credentials = credential_bindings or {}
        for item in required_configs or []:
            if not isinstance(item, dict):
                continue
            slot = str(item.get("slot") or "").strip()
            if not slot:
                errors.append("requiredConfigs 存在缺少 slot 的配置声明")
                continue
            if bool(item.get("required", False)) and not self._binding_value_exists(configs.get(slot)):
                errors.append(f"数据库/配置绑定项 {slot} 必须绑定")
        for item in required_credentials or []:
            if not isinstance(item, dict):
                continue
            slot = str(item.get("slot") or "").strip()
            if not slot:
                errors.append("requiredCredentials 存在缺少 slot 的账号声明")
                continue
            errors.extend(self._validate_credential_binding(slot, item, credentials.get(slot)))
        if errors and target_status in {"DRAFT", "ENABLED", "PAUSED", "DISABLED"}:
            raise AppError("任务契约校验未通过", code=40090, http_status=status.HTTP_400_BAD_REQUEST, data={"errors": errors})

    def _validate_owner(self, company_id: int, owner_user_id: int | None) -> int | None:
        if owner_user_id is None:
            return None
        owner = self.db.get(SysUser, owner_user_id)
        if not owner or owner.status != "ENABLED" or owner.company_id != company_id:
            raise AppError("负责人必须是所属公司的启用用户", code=40054, http_status=status.HTTP_400_BAD_REQUEST)
        return owner.user_id

    def _validate_fixed_release(self, project_id: int, company_id: int, release_id: int | None) -> int | None:
        if release_id is None:
            return None
        release = self.db.get(CrawlerProjectRelease, release_id)
        if (
            not release
            or release.project_id != project_id
            or release.company_id != company_id
            or release.release_status != "PUBLISHED"
            or release.parse_status != "SUCCESS"
        ):
            raise AppError("固定镜像版本必须属于当前项目且处于可用发布状态", code=40055, http_status=status.HTTP_400_BAD_REQUEST)
        return release.release_id

    def _validate_image_binding(self, project_id: int, company_id: int, image_policy: str, fixed_release_id: int | None) -> int | None:
        if image_policy == "PINNED":
            if not fixed_release_id:
                raise AppError("固定镜像策略必须选择发布版本", code=40056, http_status=status.HTTP_400_BAD_REQUEST)
            return self._validate_fixed_release(project_id, company_id, fixed_release_id)
        return fixed_release_id

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
        if definition.contract_status not in {"OK", "WARNING"}:
            raise AppError("任务定义契约不可用，不能创建正式任务", code=40091, http_status=status.HTTP_400_BAD_REQUEST, data={"contractStatus": definition.contract_status, "contractWarnings": definition.contract_warnings or []})
        self._validate_task_contract_bindings(
            required_configs=definition.required_configs or [],
            required_credentials=definition.required_credentials or [],
            config_bindings=payload.config_bindings or {},
            credential_bindings=payload.credential_bindings or {},
            target_status=payload.status,
        )
        task = CrawlerTask(
            company_id=project.company_id,
            project_id=project.project_id,
            definition_id=definition.definition_id,
            owner_user_id=self._validate_owner(project.company_id, payload.owner_user_id),
            task_code=payload.task_code,
            task_name=payload.task_name,
            entry_module=definition.entry_module,
            entry_function=definition.entry_function,
            parameters=payload.parameters or definition.default_params,
            config_bindings=payload.config_bindings or {},
            credential_bindings=payload.credential_bindings or {},
            contract_snapshot={
                "platformCode": definition.platform_code,
                "requiredConfigs": definition.required_configs or [],
                "requiredCredentials": definition.required_credentials or [],
                "outputTables": definition.output_tables or [],
                "contractVersion": definition.contract_version or "1",
                "contractStatus": definition.contract_status or "UNKNOWN",
                "contractWarnings": definition.contract_warnings or [],
            },
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
            fixed_release_id=self._validate_image_binding(project.project_id, project.company_id, payload.image_policy, payload.fixed_release_id),
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
                raise AppError("任务指定节点必须属于该项目已部署节点", code=40053)
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
        if "owner_user_id" in updates:
            updates["owner_user_id"] = self._validate_owner(task.company_id, updates["owner_user_id"])
        image_policy = updates.get("image_policy", task.image_policy)
        fixed_release_id = updates.get("fixed_release_id", task.fixed_release_id)
        updates["fixed_release_id"] = self._validate_image_binding(task.project_id, task.company_id, image_policy, fixed_release_id)
        if {"config_bindings", "credential_bindings", "status"} & set(updates):
            snapshot = task.contract_snapshot or {}
            self._validate_task_contract_bindings(
                required_configs=snapshot.get("requiredConfigs") or snapshot.get("required_configs") or [],
                required_credentials=snapshot.get("requiredCredentials") or snapshot.get("required_credentials") or [],
                config_bindings=updates.get("config_bindings", task.config_bindings or {}),
                credential_bindings=updates.get("credential_bindings", task.credential_bindings or {}),
                target_status=updates.get("status", task.status),
            )
        for key, value in updates.items():
            setattr(task, key, value)
        after = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        write_operation_log(self.db, user, None, operation_type="UPDATE_TASK", resource_type="task", resource_id=str(task.task_id), before_data=before, after_data=after)
        self.db.commit()
        return task

    def delete_task(self, user: SysUser, task_id: int) -> dict:
        task = self.tasks.get(task_id)
        if not task:
            raise AppError("资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_project_role(self.db, user, task.project_id, "OPERATOR")

        active_statuses = {"QUEUED", "ROUTED", "ASSIGNED", "STARTING", "RUNNING", "CANCEL_REQUESTED"}
        active_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task_id, CrawlerTaskRun.run_status.in_(active_statuses))) or 0)
        if active_count:
            raise AppError("任务存在运行中实例，不能删除，请等待结束后再操作", code=40057, http_status=status.HTTP_400_BAD_REQUEST)

        run_count = int(self.db.scalar(select(func.count()).select_from(CrawlerTaskRun).where(CrawlerTaskRun.task_id == task_id)) or 0)
        before = {c.name: getattr(task, c.name) for c in task.__table__.columns}
        schedule = self.db.scalar(select(CrawlerTaskSchedule).where(CrawlerTaskSchedule.task_id == task_id))
        project = self.projects.get(task.project_id)
        cleanup_commands = ContainerCleanupService(self.db).enqueue_task_cleanup(
            company_id=task.company_id,
            project_id=task.project_id,
            project_code=project.project_code if project else "",
            task_id=task.task_id,
            task_code=task.task_code,
            server_ids=self._cleanup_server_ids(task),
            user=user,
            reason="删除任务后清理对应任务容器",
        )

        if run_count > 0:
            task.status = "ARCHIVED"
            if schedule:
                schedule.schedule_status = "DISABLED"
                schedule.next_run_at = None
            after = {c.name: getattr(task, c.name) for c in task.__table__.columns}
            write_operation_log(self.db, user, None, operation_type="ARCHIVE_TASK", resource_type="task", resource_id=str(task.task_id), before_data=before, after_data={**after, "containerCleanupCommands": cleanup_commands})
            self.db.commit()
            return {"task_id": task_id, "deleted": False, "archived": True, "run_count": run_count, "container_cleanup_commands": cleanup_commands}

        definition_id = task.definition_id
        self.db.query(CrawlerTaskServerTarget).filter(CrawlerTaskServerTarget.task_id == task_id).delete(synchronize_session=False)
        if schedule:
            self.db.delete(schedule)
            self.db.flush()
        if definition_id:
            definition = self.db.get(CrawlerProjectTaskDefinition, definition_id)
            if definition and definition.definition_status == "CREATED":
                definition.definition_status = "AVAILABLE"
        write_operation_log(self.db, user, None, operation_type="DELETE_TASK", resource_type="task", resource_id=str(task.task_id), before_data=before, after_data={"deleted": True, "containerCleanupCommands": cleanup_commands})
        self.db.delete(task)
        self.db.commit()
        return {"task_id": task_id, "deleted": True, "archived": False, "run_count": 0, "container_cleanup_commands": cleanup_commands}

    def _cleanup_server_ids(self, task: CrawlerTask) -> list[int]:
        values: set[int] = set()
        targets = self.db.scalars(select(CrawlerTaskServerTarget.server_id).where(CrawlerTaskServerTarget.task_id == task.task_id)).all()
        values.update(int(item) for item in targets if item)
        project_servers = self.db.scalars(select(CrawlerProjectServer.server_id).where(CrawlerProjectServer.project_id == task.project_id)).all()
        values.update(int(item) for item in project_servers if item)
        run_servers = self.db.scalars(select(CrawlerTaskRun.server_id).where(CrawlerTaskRun.task_id == task.task_id, CrawlerTaskRun.server_id.is_not(None))).all()
        values.update(int(item) for item in run_servers if item)
        return sorted(values)

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
