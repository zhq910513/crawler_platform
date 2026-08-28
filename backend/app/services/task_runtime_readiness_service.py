from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CrawlerAccountCredential,
    CrawlerAgent,
    CrawlerProject,
    CrawlerProjectRelease,
    CrawlerProjectServer,
    CrawlerProjectTaskDefinition,
    CrawlerReleaseChannel,
    CrawlerServer,
    CrawlerTask,
    CrawlerTaskServerTarget,
)
from app.services.runtime_resource_service import RuntimeResourceResolver


_BAD_CREDENTIAL_HEALTH = {"UNHEALTHY", "EXPIRED", "INVALID", "LOCKED"}
_BAD_CREDENTIAL_USAGE = {"LOCKED", "DISABLED"}


@dataclass
class TaskRuntimeReadiness:
    ready: bool
    status: str
    reasons: list[str] = field(default_factory=list)
    release_id: int | None = None
    release_version: str = ""
    definition_key: str = ""
    definition_changed: bool = False
    ready_server_count: int = 0

    def asdict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "status": self.status,
            "reasons": self.reasons,
            "releaseId": self.release_id,
            "releaseVersion": self.release_version,
            "definitionKey": self.definition_key,
            "definitionChanged": self.definition_changed,
            "readyServerCount": self.ready_server_count,
        }


class TaskRuntimeReadinessService:
    """Single runtime truth used by orchestration, scheduler and manual execution."""

    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, task: CrawlerTask, *, release: CrawlerProjectRelease | None = None, require_nodes: bool = True) -> TaskRuntimeReadiness:
        reasons: list[str] = []
        project = self.db.get(CrawlerProject, task.project_id)
        if not project or project.status != "ENABLED":
            reasons.append("项目未启用")
        elif project.online_status != "ONLINE":
            reasons.append(f"项目尚未达到可运行状态：{project.online_status}")

        release = release or self.resolve_release(task)
        if not release:
            reasons.append("任务未绑定已激活且可用的 Release")
            return TaskRuntimeReadiness(False, "BLOCKED", reasons, definition_key=self._definition_key(task))

        definition = self.db.get(CrawlerProjectTaskDefinition, task.definition_id) if task.definition_id else None
        definition_key = definition.definition_key if definition else task.task_code
        if definition:
            if definition.discovery_status != "ACTIVE":
                reasons.append("任务定义已不在当前激活 Release 中")
            if definition.orchestration_status != "ORCHESTRATED":
                reasons.append("任务定义尚未处于已编排状态")

        manifest_definition = self._manifest_definition(release, definition_key)
        definition_changed = False
        if not manifest_definition:
            reasons.append(f"当前激活 Release 未包含任务定义 {definition_key}")
            definition_changed = True
        else:
            drift = self._definition_drift(task, manifest_definition)
            if drift:
                definition_changed = True
                reasons.extend(drift)
            reasons.extend(self._binding_errors(task, manifest_definition))

        ready_server_count = self._ready_server_count(task, release.release_id)
        if require_nodes:
            required_nodes = max(1, task.required_node_count or 1)
            explicit_targets = bool(
                self.db.scalar(
                    select(func.count(CrawlerTaskServerTarget.target_id)).where(
                        CrawlerTaskServerTarget.task_id == task.task_id,
                        CrawlerTaskServerTarget.enabled.is_(True),
                    )
                )
            )
            if ready_server_count < required_nodes and explicit_targets:
                reasons.append(f"任务指定节点当前不可运行：{ready_server_count}/{required_nodes}")
            elif ready_server_count < required_nodes and not project.allow_company_pool_fallback:
                reasons.append(f"当前 Release 可运行节点不足：{ready_server_count}/{required_nodes}")
            elif ready_server_count < required_nodes and project.allow_company_pool_fallback and not self._has_company_fallback(task):
                reasons.append(f"当前 Release 可运行节点不足，且公司节点兜底不可用：{ready_server_count}/{required_nodes}")

        return TaskRuntimeReadiness(
            ready=not reasons,
            status="READY" if not reasons else ("NEEDS_REVIEW" if definition_changed else "BLOCKED"),
            reasons=reasons,
            release_id=release.release_id,
            release_version=release.version,
            definition_key=definition_key,
            definition_changed=definition_changed,
            ready_server_count=ready_server_count,
        )

    def resolve_release(self, task: CrawlerTask) -> CrawlerProjectRelease | None:
        if task.image_policy == "PINNED":
            release = self.db.get(CrawlerProjectRelease, task.fixed_release_id) if task.fixed_release_id else None
        else:
            channel = self.db.scalar(
                select(CrawlerReleaseChannel).where(
                    CrawlerReleaseChannel.project_id == task.project_id,
                    CrawlerReleaseChannel.channel_name == task.release_channel,
                    CrawlerReleaseChannel.channel_status == "ENABLED",
                )
            )
            release = self.db.get(CrawlerProjectRelease, channel.release_id) if channel and channel.release_id else None
        if not release:
            return None
        if release.project_id != task.project_id or release.company_id != task.company_id:
            return None
        if release.release_status != "PUBLISHED" or release.parse_status != "SUCCESS":
            return None
        return release

    def _binding_errors(self, task: CrawlerTask, item: dict[str, Any]) -> list[str]:
        errors = RuntimeResourceResolver(self.db).validate_bindings(
            company_id=task.company_id,
            project_id=task.project_id,
            required_configs=item.get("requiredConfigs") or item.get("required_configs") or [],
            config_bindings=task.config_bindings or {},
        )
        credentials = task.credential_bindings or {}
        for requirement in item.get("requiredCredentials") or item.get("required_credentials") or []:
            if not isinstance(requirement, dict):
                continue
            slot = str(requirement.get("slot") or "").strip()
            if not slot:
                errors.append("requiredCredentials 存在缺少 slot 的声明")
                continue
            binding = credentials.get(slot)
            if bool(requirement.get("required", False)) and not self._binding_exists(binding):
                errors.append(f"账号绑定项 {slot} 必须配置")
                continue
            if not self._binding_exists(binding):
                continue
            errors.extend(self._credential_runtime_errors(task.company_id, slot, requirement, binding))
        return errors

    def _credential_runtime_errors(self, company_id: int, slot: str, requirement: dict[str, Any], binding: Any) -> list[str]:
        errors: list[str] = []
        mode = self._credential_mode(binding)
        allowed = {str(item) for item in (requirement.get("supportedModes") or requirement.get("supported_modes") or ["fixed"])}
        if mode not in allowed:
            return [f"账号绑定项 {slot} 不支持模式 {mode}"]
        expected_platform = str(requirement.get("platformCode") or requirement.get("platform_code") or "").strip().lower()
        if mode == "fixed":
            key = self._credential_key(binding)
            if not key:
                return [f"账号绑定项 {slot} fixed 模式缺少账号"]
            credential = self.db.scalar(
                select(CrawlerAccountCredential).where(
                    CrawlerAccountCredential.company_id == company_id,
                    CrawlerAccountCredential.credential_key == key,
                    *([CrawlerAccountCredential.platform_code == expected_platform] if expected_platform else []),
                )
            )
            if not credential:
                errors.append(f"账号绑定项 {slot} 未找到账号 {key}")
            elif not self._credential_usable(credential):
                errors.append(f"账号绑定项 {slot} 的账号 {key} 当前不可用")
        elif mode == "fixed_list":
            keys = self._credential_keys(binding)
            if not keys:
                errors.append(f"账号绑定项 {slot} fixed_list 模式账号列表为空")
            for key in keys:
                credential = self.db.scalar(
                    select(CrawlerAccountCredential).where(
                        CrawlerAccountCredential.company_id == company_id,
                        CrawlerAccountCredential.credential_key == key,
                        *([CrawlerAccountCredential.platform_code == expected_platform] if expected_platform else []),
                    )
                )
                if not credential or not self._credential_usable(credential):
                    errors.append(f"账号绑定项 {slot} 的账号 {key} 当前不可用")
        elif mode in {"pool", "affinity_pool", "external_affinity_pool", "binding_rule"}:
            if expected_platform:
                count = int(
                    self.db.scalar(
                        select(func.count(CrawlerAccountCredential.credential_id)).where(
                            CrawlerAccountCredential.company_id == company_id,
                            CrawlerAccountCredential.platform_code == expected_platform,
                            CrawlerAccountCredential.enabled.is_(True),
                            CrawlerAccountCredential.health_status.notin_(list(_BAD_CREDENTIAL_HEALTH)),
                            CrawlerAccountCredential.usage_status.notin_(list(_BAD_CREDENTIAL_USAGE)),
                        )
                    )
                    or 0
                )
                if count == 0:
                    errors.append(f"账号绑定项 {slot} 没有可用的 {expected_platform} 账号池")
        return errors

    def _definition_drift(self, task: CrawlerTask, item: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        entry_module = str(item.get("entryModule") or item.get("entry_module") or "")
        entry_function = str(item.get("entryFunction") or item.get("entry_function") or "")
        if entry_module != task.entry_module or entry_function != task.entry_function:
            errors.append("任务入口已随 Release 变化，需要重新编排确认")
        execution_mode = str(item.get("executionMode") or item.get("execution_mode") or "SINGLE")
        if execution_mode != task.execution_mode:
            errors.append("任务执行模式已随 Release 变化，需要重新编排确认")
        idempotency = str(item.get("idempotencyPolicy") or item.get("idempotency_policy") or "IDEMPOTENT")
        if idempotency != task.idempotency_policy:
            errors.append("任务幂等策略已随 Release 变化，需要重新编排确认")
        snapshot = task.contract_snapshot or {}
        for camel, snake, label in (
            ("requiredConfigs", "required_configs", "配置依赖"),
            ("requiredCredentials", "required_credentials", "账号依赖"),
        ):
            before = snapshot.get(camel) or snapshot.get(snake) or []
            after = item.get(camel) or item.get(snake) or []
            if self._canonical(before) != self._canonical(after):
                errors.append(f"任务{label}已随 Release 变化，需要重新编排确认")
        return errors

    def _ready_server_count(self, task: CrawlerTask, release_id: int) -> int:
        target_ids = list(
            self.db.scalars(
                select(CrawlerTaskServerTarget.server_id).where(
                    CrawlerTaskServerTarget.task_id == task.task_id,
                    CrawlerTaskServerTarget.enabled.is_(True),
                )
            ).all()
        )
        stmt = (
            select(func.count(CrawlerProjectServer.project_server_id))
            .join(CrawlerServer, CrawlerServer.server_id == CrawlerProjectServer.server_id)
            .join(CrawlerAgent, CrawlerAgent.server_id == CrawlerServer.server_id)
            .where(
                CrawlerProjectServer.project_id == task.project_id,
                CrawlerProjectServer.latest_release_id == release_id,
                CrawlerProjectServer.deployment_status == "DEPLOYED",
                CrawlerProjectServer.image_readiness_status == "READY",
                CrawlerProjectServer.scheduling_status.in_(["ENABLED", "RECOVERING"]),
                CrawlerServer.manage_status == "ENABLED",
                CrawlerServer.health_status.in_(["HEALTHY", "DEGRADED"]),
                CrawlerServer.capacity_status.in_(["NORMAL", "PRESSURE"]),
                CrawlerAgent.connection_status == "ONLINE",
            )
        )
        if target_ids:
            stmt = stmt.where(CrawlerProjectServer.server_id.in_(target_ids))
        return int(self.db.scalar(stmt) or 0)

    def _has_company_fallback(self, task: CrawlerTask) -> bool:
        stmt = (
            select(func.count(CrawlerServer.server_id))
            .join(CrawlerAgent, CrawlerAgent.server_id == CrawlerServer.server_id)
            .where(
                CrawlerServer.company_id == task.company_id,
                CrawlerServer.manage_status == "ENABLED",
                CrawlerServer.health_status.in_(["HEALTHY", "DEGRADED"]),
                CrawlerServer.capacity_status.in_(["NORMAL", "PRESSURE"]),
                CrawlerAgent.connection_status == "ONLINE",
            )
        )
        return int(self.db.scalar(stmt) or 0) > 0

    @staticmethod
    def _manifest_definition(release: CrawlerProjectRelease, definition_key: str) -> dict[str, Any] | None:
        for item in (release.manifest or {}).get("taskDefinitions") or []:
            if isinstance(item, dict) and str(item.get("definitionKey") or "").strip() == definition_key:
                return item
        return None

    @staticmethod
    def _definition_key(task: CrawlerTask) -> str:
        return task.task_code or ""

    @staticmethod
    def _binding_exists(value: Any) -> bool:
        return value is not None and value != "" and value != {} and value != []

    @staticmethod
    def _credential_mode(binding: Any) -> str:
        if isinstance(binding, str):
            return "fixed"
        if isinstance(binding, list):
            return "fixed_list"
        if isinstance(binding, dict):
            return str(binding.get("mode") or "fixed").strip()
        return ""

    @staticmethod
    def _credential_key(binding: Any) -> str:
        if isinstance(binding, str):
            return binding.strip()
        if isinstance(binding, dict):
            value = binding.get("credentialKey") or binding.get("credential_key") or binding.get("credentialRef") or binding.get("credential_ref")
            return str(value or "").strip()
        return ""

    @classmethod
    def _credential_keys(cls, binding: Any) -> list[str]:
        if isinstance(binding, list):
            return [str(item).strip() for item in binding if str(item).strip()]
        if isinstance(binding, dict):
            values = binding.get("credentialKeys") or binding.get("credential_keys") or binding.get("credentialRefs") or binding.get("credential_refs") or []
            if isinstance(values, list):
                return [str(item).strip() for item in values if str(item).strip()]
        return []

    @staticmethod
    def _credential_usable(credential: CrawlerAccountCredential) -> bool:
        return bool(
            credential.enabled
            and credential.health_status not in _BAD_CREDENTIAL_HEALTH
            and credential.usage_status not in _BAD_CREDENTIAL_USAGE
        )

    @staticmethod
    def _canonical(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
