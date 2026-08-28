from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrawlerProject, CrawlerProjectRelease, CrawlerProjectTaskDefinition, CrawlerTask
from app.utils import utcnow


class TaskDefinitionLifecycleService:
    """Own manifest-driven task definition facts without overwriting user decisions."""

    def __init__(self, db: Session):
        self.db = db

    def sync_from_release(self, project: CrawlerProject, release: CrawlerProjectRelease) -> dict[str, int]:
        task_items = (release.manifest or {}).get("taskDefinitions") or []
        seen: set[str] = set()
        created = 0
        updated = 0
        restored = 0
        now = utcnow()
        for item in task_items:
            if not isinstance(item, dict):
                continue
            key = str(item.get("definitionKey") or "").strip()
            if not key:
                continue
            seen.add(key)
            definition = self.db.scalar(
                select(CrawlerProjectTaskDefinition).where(
                    CrawlerProjectTaskDefinition.project_id == project.project_id,
                    CrawlerProjectTaskDefinition.definition_key == key,
                )
            )
            if not definition:
                definition = CrawlerProjectTaskDefinition(
                    company_id=project.company_id,
                    project_id=project.project_id,
                    definition_key=key,
                    discovery_status="ACTIVE",
                    orchestration_status="PENDING",
                    first_seen_release_id=release.release_id,
                )
                self.db.add(definition)
                created += 1
            else:
                if definition.discovery_status in {"REMOVED", "INVALID"}:
                    restored += 1
                updated += 1
            definition.discovery_status = "ACTIVE"
            definition.latest_release_id = release.release_id
            definition.first_seen_release_id = definition.first_seen_release_id or release.release_id
            definition.last_seen_at = now
            definition.task_name = item.get("taskName", key)
            definition.entry_module = item.get("entryModule", "")
            definition.entry_function = item.get("entryFunction", "")
            definition.source_file = item.get("sourceFile", "sch.py")
            definition.source_fingerprint = item.get("sourceFingerprint", "")
            definition.default_params = item.get("defaultParams") or {}
            definition.suggested_cron = item.get("suggestedCron", "")
            definition.execution_mode = item.get("executionMode", "SINGLE")
            definition.idempotency_policy = item.get("idempotencyPolicy", "IDEMPOTENT")
            definition.resource_requirements = item.get("resourceRequirements") or {}
            definition.required_capabilities = item.get("requiredCapabilities") or {}
            definition.platform_code = str(item.get("platformCode") or item.get("platform_code") or "").strip().lower()
            definition.required_configs = item.get("requiredConfigs") or item.get("required_configs") or []
            definition.required_credentials = item.get("requiredCredentials") or item.get("required_credentials") or []
            definition.output_tables = item.get("outputTables") or item.get("output_tables") or []
            definition.contract_version = str(item.get("contractVersion") or item.get("contract_version") or "1")
            definition.contract_status, definition.contract_warnings = self.validate_contract(item)
            definition.runtime_mode = item.get("runtimeMode", "SHARED_ENV_ISOLATED")
            definition.task_group = item.get("taskGroup", "default")
            definition.task_max_concurrency = int(item.get("taskMaxConcurrency", 1) or 1)
            definition.group_max_concurrency = int(item.get("groupMaxConcurrency", 4) or 4)
            definition.exclusive_mode = bool(item.get("exclusiveMode", False))
            definition.io_class = item.get("ioClass", "NORMAL")
            definition.shm_size_mb = int(item.get("shmSizeMb", 64) or 64)
            definition.log_limit_mb = int(item.get("logLimitMb", 50) or 50)
            locks = item.get("resourceLocks") or []
            definition.resource_locks = locks if isinstance(locks, list) else []
            definition.secret_refs = item.get("secretRefs") or []
            definition.allow_offline_run = bool(item.get("allowOfflineRun", False))
            definition.offline_policy = item.get("offlinePolicy") or {}
            definition.parse_message = ""

        removed = 0
        definitions = list(
            self.db.scalars(
                select(CrawlerProjectTaskDefinition).where(CrawlerProjectTaskDefinition.project_id == project.project_id)
            ).all()
        )
        for definition in definitions:
            if definition.definition_key in seen:
                continue
            if definition.discovery_status != "REMOVED":
                removed += 1
            definition.discovery_status = "REMOVED"
            definition.parse_message = "当前激活 Release 的 manifest 中未发现该任务定义"
        self.db.flush()
        return {"created": created, "updated": updated, "restored": restored, "removed": removed, "active": len(seen)}

    def ignore(self, definition: CrawlerProjectTaskDefinition, *, user_id: int, reason: str = "") -> CrawlerProjectTaskDefinition:
        if definition.discovery_status != "ACTIVE":
            raise ValueError("only active definitions can be ignored")
        existing = self.db.scalar(select(CrawlerTask.task_id).where(CrawlerTask.project_id == definition.project_id, CrawlerTask.definition_id == definition.definition_id))
        if existing or definition.orchestration_status == "ORCHESTRATED":
            raise ValueError("orchestrated definitions cannot be ignored")
        definition.orchestration_status = "IGNORED"
        definition.ignored_at = utcnow()
        definition.ignored_by = user_id
        definition.ignore_reason = (reason or "")[:500]
        self.db.flush()
        return definition

    def restore(self, definition: CrawlerProjectTaskDefinition) -> CrawlerProjectTaskDefinition:
        if definition.orchestration_status != "IGNORED":
            raise ValueError("only ignored definitions can be restored")
        existing = self.db.scalar(select(CrawlerTask.task_id).where(CrawlerTask.project_id == definition.project_id, CrawlerTask.definition_id == definition.definition_id))
        definition.orchestration_status = "ORCHESTRATED" if existing else "PENDING"
        definition.ignored_at = None
        definition.ignored_by = None
        definition.ignore_reason = ""
        self.db.flush()
        return definition

    @staticmethod
    def validate_contract(item: dict) -> tuple[str, list[str]]:
        warnings: list[str] = []
        platform_code = str(item.get("platformCode") or item.get("platform_code") or "").strip().lower()
        if not platform_code:
            warnings.append("缺少 platformCode，平台任务无法在前端按被爬平台归类")
        required_credentials = item.get("requiredCredentials") or item.get("required_credentials") or []
        if required_credentials and not isinstance(required_credentials, list):
            warnings.append("requiredCredentials 必须是列表")
        for idx, cred in enumerate(required_credentials if isinstance(required_credentials, list) else [], start=1):
            if not isinstance(cred, dict):
                warnings.append(f"requiredCredentials[{idx}] 必须是对象")
                continue
            if not str(cred.get("slot") or "").strip():
                warnings.append(f"requiredCredentials[{idx}] 缺少 slot")
            if not str(cred.get("platformCode") or cred.get("platform_code") or platform_code or "").strip():
                warnings.append(f"requiredCredentials[{idx}] 缺少 platformCode")
            modes = cred.get("supportedModes") or cred.get("supported_modes") or []
            if modes and not isinstance(modes, list):
                warnings.append(f"requiredCredentials[{idx}].supportedModes 必须是列表")
        required_configs = item.get("requiredConfigs") or item.get("required_configs") or []
        if required_configs and not isinstance(required_configs, list):
            warnings.append("requiredConfigs 必须是列表")
        for idx, cfg in enumerate(required_configs if isinstance(required_configs, list) else [], start=1):
            if not isinstance(cfg, dict):
                warnings.append(f"requiredConfigs[{idx}] 必须是对象")
                continue
            if not str(cfg.get("slot") or "").strip():
                warnings.append(f"requiredConfigs[{idx}] 缺少 slot")
            if not str(cfg.get("type") or cfg.get("configType") or "").strip():
                warnings.append(f"requiredConfigs[{idx}] 缺少 type/configType")
        output_tables = item.get("outputTables") or item.get("output_tables") or []
        if output_tables and not isinstance(output_tables, list):
            warnings.append("outputTables 必须是列表")
        for idx, table in enumerate(output_tables if isinstance(output_tables, list) else [], start=1):
            if not isinstance(table, dict):
                warnings.append(f"outputTables[{idx}] 必须是对象")
                continue
            if not str(table.get("slot") or "").strip():
                warnings.append(f"outputTables[{idx}] 缺少 slot")
        return ("WARNING" if warnings else "OK"), warnings
