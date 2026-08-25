from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CompanyResourceConfig, CrawlerTask
from app.security import decrypt_secret
from app.services.company_resource_service import COMPLETE_STATUSES


ENGINE_ALIASES = {
    "MONGO": "MONGODB",
    "MONGODB": "MONGODB",
    "MYSQL": "MYSQL",
    "POSTGRES": "POSTGRESQL",
    "POSTGRESQL": "POSTGRESQL",
    "SQLSERVER": "SQLSERVER",
    "SQL_SERVER": "SQLSERVER",
    "REDIS": "REDIS",
    "OSS": "ALIYUN_OSS",
    "ALIYUN_OSS": "ALIYUN_OSS",
    "S3": "S3",
    "MINIO": "MINIO",
}


@dataclass(slots=True, frozen=True)
class ConfigRequirement:
    slot: str
    required: bool
    expected_engine: str


@dataclass(slots=True, frozen=True)
class ConfigBindingRef:
    slot: str
    resource_id: int | None
    resource_code: str
    raw: Any


class RuntimeResourceResolver:
    """Resolve company resource bindings for a single run claim.

    Run snapshots keep only binding references. This resolver is intentionally
    used at Agent claim time so decrypted connection config is delivered only to
    the task container and is not persisted into crawler_task_run.parameters_snapshot.
    """

    def __init__(self, db: Session):
        self.db = db

    def validate_bindings(
        self,
        *,
        company_id: int,
        project_id: int,
        required_configs: list[Any] | None,
        config_bindings: dict[str, Any] | None,
    ) -> list[str]:
        errors: list[str] = []
        requirements = self._requirements(required_configs)
        bindings = config_bindings or {}
        for slot, requirement in requirements.items():
            raw = bindings.get(slot)
            if requirement.required and not self._binding_exists(raw):
                errors.append(f"数据库/配置绑定项 {slot} 必须绑定")
                continue
            if not self._binding_exists(raw):
                continue
            ref = self._binding_ref(slot, raw)
            if not ref:
                errors.append(f"数据库/配置绑定项 {slot} 绑定格式无效")
                continue
            resource = self._find_resource(company_id=company_id, project_id=project_id, ref=ref)
            if not resource:
                errors.append(f"数据库/配置绑定项 {slot} 未找到可用公司资源配置")
                continue
            errors.extend(self._validate_resource(slot, requirement, resource))
        return errors

    def resolve_for_task(self, task: CrawlerTask, runtime_parameters: dict[str, Any] | None) -> dict[str, Any]:
        params = runtime_parameters if isinstance(runtime_parameters, dict) else {}
        bindings = params.get("configBindings") or params.get("config_bindings") or task.config_bindings or {}
        if not isinstance(bindings, dict):
            bindings = {}
        requirements = self._requirements((task.contract_snapshot or {}).get("requiredConfigs") or (task.contract_snapshot or {}).get("required_configs") or [])
        resolved: dict[str, Any] = {}
        errors: list[str] = []
        slots = set(bindings.keys()) | {slot for slot, req in requirements.items() if req.required}
        for slot in sorted(str(item) for item in slots if str(item)):
            requirement = requirements.get(slot, ConfigRequirement(slot=slot, required=False, expected_engine=""))
            raw = bindings.get(slot)
            if requirement.required and not self._binding_exists(raw):
                errors.append(f"数据库/配置绑定项 {slot} 必须绑定")
                continue
            if not self._binding_exists(raw):
                continue
            ref = self._binding_ref(slot, raw)
            if not ref:
                if requirement.required:
                    errors.append(f"数据库/配置绑定项 {slot} 绑定格式无效")
                continue
            resource = self._find_resource(company_id=task.company_id, project_id=task.project_id, ref=ref)
            if not resource:
                if requirement.required:
                    errors.append(f"数据库/配置绑定项 {slot} 未找到可用公司资源配置")
                continue
            resource_errors = self._validate_resource(slot, requirement, resource)
            if resource_errors:
                errors.extend(resource_errors)
                continue
            config = self._decrypt_config(resource)
            if not config and requirement.required:
                errors.append(f"数据库/配置绑定项 {slot} 对应资源配置为空或无法解密")
                continue
            resolved[slot] = {
                **config,
                "resourceId": resource.resource_id,
                "resourceCode": resource.resource_code,
                "resourceName": resource.resource_name,
                "resourceCategory": resource.resource_category,
                "resourceEngine": resource.resource_engine,
                "resourceRole": resource.resource_role,
                "connectionMode": resource.connection_mode,
            }
        if errors:
            raise AppError("运行时资源配置解析失败", code=40096, http_status=status.HTTP_400_BAD_REQUEST, data={"errors": errors})
        return resolved

    @staticmethod
    def _requirements(required_configs: list[Any] | None) -> dict[str, ConfigRequirement]:
        result: dict[str, ConfigRequirement] = {}
        for item in required_configs or []:
            if not isinstance(item, dict):
                continue
            slot = str(item.get("slot") or "").strip()
            if not slot:
                continue
            raw_engine = item.get("type") or item.get("configType") or item.get("config_type") or item.get("resourceEngine") or item.get("resource_engine") or ""
            expected_engine = ENGINE_ALIASES.get(str(raw_engine).strip().upper(), str(raw_engine).strip().upper()) if raw_engine else ""
            result[slot] = ConfigRequirement(slot=slot, required=bool(item.get("required", False)), expected_engine=expected_engine)
        return result

    @staticmethod
    def _binding_exists(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, dict):
            return any(value.get(key) not in (None, "", []) for key in ("resourceId", "resource_id", "configId", "config_id", "resourceCode", "resource_code", "configRef", "config_ref", "resourceRef", "resource_ref", "ref"))
        return True

    @staticmethod
    def _binding_ref(slot: str, raw: Any) -> ConfigBindingRef | None:
        if isinstance(raw, int):
            return ConfigBindingRef(slot=slot, resource_id=raw, resource_code="", raw=raw)
        if isinstance(raw, str):
            value = raw.strip()
            if not value:
                return None
            if value.isdigit():
                return ConfigBindingRef(slot=slot, resource_id=int(value), resource_code="", raw=raw)
            for prefix in ("config:", "resource:", "company_resource:"):
                if value.startswith(prefix):
                    value = value[len(prefix):].strip()
                    break
            return ConfigBindingRef(slot=slot, resource_id=None, resource_code=value, raw=raw)
        if isinstance(raw, dict):
            resource_id = raw.get("resourceId") or raw.get("resource_id") or raw.get("configId") or raw.get("config_id")
            try:
                parsed_id = int(resource_id) if resource_id not in (None, "") else None
            except Exception:
                parsed_id = None
            code = raw.get("resourceCode") or raw.get("resource_code") or raw.get("configCode") or raw.get("config_code") or raw.get("resourceRef") or raw.get("resource_ref") or raw.get("configRef") or raw.get("config_ref") or raw.get("ref") or ""
            code = str(code).strip()
            for prefix in ("config:", "resource:", "company_resource:"):
                if code.startswith(prefix):
                    code = code[len(prefix):].strip()
                    break
            if parsed_id is None and not code:
                return None
            return ConfigBindingRef(slot=slot, resource_id=parsed_id, resource_code=code, raw=raw)
        return None

    def _find_resource(self, *, company_id: int, project_id: int, ref: ConfigBindingRef) -> CompanyResourceConfig | None:
        conditions = [CompanyResourceConfig.company_id == company_id, or_(CompanyResourceConfig.project_id.is_(None), CompanyResourceConfig.project_id == project_id)]
        if ref.resource_id is not None:
            conditions.append(CompanyResourceConfig.resource_id == ref.resource_id)
        else:
            conditions.append(CompanyResourceConfig.resource_code == ref.resource_code)
        stmt = select(CompanyResourceConfig).where(and_(*conditions)).order_by(CompanyResourceConfig.project_id.desc().nullslast(), CompanyResourceConfig.resource_id.desc()).limit(1)
        return self.db.scalar(stmt)

    @staticmethod
    def _validate_resource(slot: str, requirement: ConfigRequirement, resource: CompanyResourceConfig) -> list[str]:
        errors: list[str] = []
        if not resource.enabled:
            errors.append(f"数据库/配置绑定项 {slot} 对应资源已停用：{resource.resource_code}")
        if resource.test_status not in COMPLETE_STATUSES:
            errors.append(f"数据库/配置绑定项 {slot} 对应资源未通过配置校验：{resource.resource_code} / {resource.test_status}")
        if requirement.expected_engine and resource.resource_engine != requirement.expected_engine:
            errors.append(f"数据库/配置绑定项 {slot} 类型不匹配：期望 {requirement.expected_engine}，实际 {resource.resource_engine}")
        return errors

    @staticmethod
    def _decrypt_config(resource: CompanyResourceConfig) -> dict[str, Any]:
        try:
            import json

            data = json.loads(decrypt_secret(resource.config_encrypted))
            if isinstance(data, dict) and isinstance(data.get("config"), dict):
                return dict(data.get("config") or {})
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}
