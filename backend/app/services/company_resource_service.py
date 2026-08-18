from __future__ import annotations

import json
from typing import Any

from fastapi import status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CompanyResourceConfig, CrawlerCompany, CrawlerProject, SysSecret, SysUser
from app.schemas import CompanyResourceConfigCreate, CompanyResourceConfigTest, CompanyResourceStatusUpdate
from app.security import decrypt_secret, encrypt_secret
from app.services.audit import write_operation_log
from app.services.permissions import require_company_scope, scoped_company_id
from app.services.resource_config_summary import build_config_summary, build_connection_summary, mask_config
from app.services.resource_config_validator import (
    LEGACY_RESOURCE_TYPE_MAP,
    RESOURCE_CATEGORY_LABELS,
    RESOURCE_ENGINE_LABELS,
    RESOURCE_ROLE_LABELS,
    validate_resource_config,
    validate_resource_shape,
)
from app.utils import utcnow

COMPLETE_STATUSES = {"CONFIG_VALID", "CONNECTION_PASSED", "MANUAL_CONFIRMED"}
SECRET_PLACEHOLDER = "******"


def _legacy_secret_prefix(company_id: int) -> str:
    return f"company_resource:{company_id}:"


class CompanyResourceService:
    def __init__(self, db: Session):
        self.db = db

    def list_resources(
        self,
        user: SysUser,
        company_id: int | None = None,
        project_id: int | None = None,
        resource_category: str | None = None,
        resource_engine: str | None = None,
        resource_role: str | None = None,
        enabled: bool | None = None,
        test_status: str | None = None,
        keyword: str | None = None,
    ) -> list[dict[str, Any]]:
        scoped = scoped_company_id(user, company_id)
        if scoped is None:
            raise AppError("请选择公司", code=40081)
        stmt = select(CompanyResourceConfig).where(CompanyResourceConfig.company_id == scoped)
        if project_id is not None:
            self._ensure_project(scoped, project_id)
            stmt = stmt.where(CompanyResourceConfig.project_id == project_id)
        if resource_category:
            stmt = stmt.where(CompanyResourceConfig.resource_category == resource_category)
        if resource_engine:
            stmt = stmt.where(CompanyResourceConfig.resource_engine == resource_engine)
        if resource_role:
            stmt = stmt.where(CompanyResourceConfig.resource_role == resource_role)
        if enabled is not None:
            stmt = stmt.where(CompanyResourceConfig.enabled.is_(enabled))
        if test_status:
            stmt = stmt.where(CompanyResourceConfig.test_status == test_status)
        if keyword:
            like = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(CompanyResourceConfig.resource_name.like(like), CompanyResourceConfig.resource_code.like(like), CompanyResourceConfig.remark.like(like)))
        stmt = stmt.order_by(CompanyResourceConfig.updated_at.desc(), CompanyResourceConfig.resource_id.desc())
        return [self._to_public(item) for item in self.db.scalars(stmt).all()]

    def upsert_resource(self, user: SysUser, payload: CompanyResourceConfigCreate) -> dict[str, Any]:
        require_company_scope(user, payload.company_id)
        if not self.db.get(CrawlerCompany, payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        if payload.project_id is not None:
            self._ensure_project(payload.company_id, payload.project_id)
        shape_errors = validate_resource_shape(payload.resource_category, payload.resource_engine, payload.connection_mode)
        if shape_errors:
            raise AppError("；".join(shape_errors), code=40082)
        exists = self.db.scalar(
            select(CompanyResourceConfig).where(
                CompanyResourceConfig.company_id == payload.company_id,
                CompanyResourceConfig.resource_code == payload.resource_code,
                CompanyResourceConfig.resource_id != (payload.resource_id or 0),
            )
        )
        if exists:
            raise AppError("同一公司内资源编码已存在，请换一个资源编码", code=40083)
        item: CompanyResourceConfig | None = self.db.get(CompanyResourceConfig, payload.resource_id) if payload.resource_id else None
        if payload.resource_id and (not item or item.company_id != payload.company_id):
            raise AppError("数据资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        existing_config = self._decrypt_config(item) if item else {}
        config = self._merge_preserved_secrets(existing_config, payload.config)
        masked = mask_config(config)
        summary = build_config_summary(payload.resource_engine, payload.connection_mode, config)
        now = utcnow()
        if item is None:
            item = CompanyResourceConfig(
                company_id=payload.company_id,
                created_by=user.user_id,
                config_encrypted=encrypt_secret(json.dumps(config, ensure_ascii=False)),
            )
            self.db.add(item)
        item.project_id = payload.project_id
        item.resource_name = payload.resource_name
        item.resource_code = payload.resource_code
        item.resource_category = payload.resource_category
        item.resource_engine = payload.resource_engine
        item.resource_role = payload.resource_role
        item.connection_mode = payload.connection_mode
        item.config_encrypted = encrypt_secret(json.dumps(config, ensure_ascii=False))
        item.config_masked_snapshot = masked
        item.config_summary = summary
        item.remark = payload.remark
        item.enabled = payload.enabled
        item.test_status = "NOT_TESTED"
        item.last_test_at = None
        item.last_test_message = "保存成功，尚未执行基础配置校验。"
        item.updated_by = user.user_id
        item.updated_at = now
        self.db.flush()
        write_operation_log(
            self.db,
            user,
            None,
            operation_type="UPSERT_COMPANY_RESOURCE",
            resource_type="company_resource",
            resource_id=str(item.resource_id),
            after_data={"companyId": payload.company_id, "resourceCode": payload.resource_code, "resourceEngine": payload.resource_engine, "resourceRole": payload.resource_role},
        )
        self.db.commit()
        return self._to_public(item)

    def test_resource(self, user: SysUser, config_id: int, payload: CompanyResourceConfigTest) -> dict[str, Any]:
        item = self.db.get(CompanyResourceConfig, config_id)
        if not item:
            raise AppError("数据资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, item.company_id)
        if payload.force_success:
            status_text, message = "MANUAL_CONFIRMED", "已人工确认可用，平台未执行真实连通测试。"
        else:
            status_text, message = validate_resource_config(item.resource_engine, item.connection_mode, self._decrypt_config(item))
        item.test_status = status_text
        item.last_test_at = utcnow()
        item.last_test_message = message
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="TEST_COMPANY_RESOURCE", resource_type="company_resource", resource_id=str(config_id), after_data={"testStatus": status_text, "message": message})
        self.db.commit()
        return self._to_public(item)

    def update_status(self, user: SysUser, config_id: int, payload: CompanyResourceStatusUpdate) -> dict[str, Any]:
        item = self.db.get(CompanyResourceConfig, config_id)
        if not item:
            raise AppError("数据资源不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, item.company_id)
        item.enabled = payload.enabled
        item.updated_by = user.user_id
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="UPDATE_COMPANY_RESOURCE_STATUS", resource_type="company_resource", resource_id=str(config_id), after_data={"enabled": payload.enabled})
        self.db.commit()
        return self._to_public(item)

    def legacy_resources(self, company_id: int) -> list[dict[str, Any]]:
        stmt = select(SysSecret).where(SysSecret.company_id == company_id, SysSecret.secret_code.like(f"{_legacy_secret_prefix(company_id)}%"), SysSecret.enabled.is_(True))
        return [self._legacy_to_public(item) for item in self.db.scalars(stmt).all()]

    def _to_public(self, item: CompanyResourceConfig) -> dict[str, Any]:
        config = self._decrypt_config(item)
        masked = item.config_masked_snapshot or mask_config(config)
        summary = item.config_summary or build_config_summary(item.resource_engine, item.connection_mode, config)
        return {
            "configId": item.resource_id,
            "resourceId": item.resource_id,
            "companyId": item.company_id,
            "projectId": item.project_id,
            "resourceName": item.resource_name,
            "resourceCode": item.resource_code,
            "resourceCategory": item.resource_category,
            "resourceEngine": item.resource_engine,
            "resourceRole": item.resource_role,
            "connectionMode": item.connection_mode,
            "categoryLabel": RESOURCE_CATEGORY_LABELS.get(item.resource_category, item.resource_category),
            "engineLabel": RESOURCE_ENGINE_LABELS.get(item.resource_engine, item.resource_engine),
            "roleLabel": RESOURCE_ROLE_LABELS.get(item.resource_role, item.resource_role),
            "resourceLabel": f"{RESOURCE_ENGINE_LABELS.get(item.resource_engine, item.resource_engine)} / {RESOURCE_ROLE_LABELS.get(item.resource_role, item.resource_role)}",
            "connectionSummary": build_connection_summary(item.resource_engine, item.connection_mode, config),
            "configSummary": summary,
            "configMasked": masked,
            "remark": item.remark,
            "enabled": item.enabled,
            "testStatus": item.test_status,
            "lastTestAt": item.last_test_at,
            "lastTestMessage": item.last_test_message,
            "legacyResourceType": item.legacy_resource_type,
            "updatedAt": item.updated_at,
        }

    def _legacy_to_public(self, item: SysSecret) -> dict[str, Any]:
        legacy_type = item.secret_code.split(":")[-1]
        category, engine, role, mode, code, default_name = LEGACY_RESOURCE_TYPE_MAP.get(legacy_type, ("OTHER", "OTHER", "OTHER", "HOST_PORT", legacy_type.lower(), legacy_type))
        return {
            "configId": item.secret_id,
            "resourceId": item.secret_id,
            "companyId": item.company_id,
            "projectId": item.project_id,
            "resourceName": item.secret_name or default_name,
            "resourceCode": code,
            "resourceCategory": category,
            "resourceEngine": engine,
            "resourceRole": role,
            "connectionMode": mode,
            "categoryLabel": RESOURCE_CATEGORY_LABELS.get(category, category),
            "engineLabel": RESOURCE_ENGINE_LABELS.get(engine, engine),
            "roleLabel": RESOURCE_ROLE_LABELS.get(role, role),
            "resourceLabel": f"{RESOURCE_ENGINE_LABELS.get(engine, engine)} / {RESOURCE_ROLE_LABELS.get(role, role)}",
            "connectionSummary": "旧版配置，待迁移",
            "configSummary": {},
            "configMasked": {},
            "remark": f"由系统从旧版 {legacy_type} 自动兼容展示。",
            "enabled": item.enabled,
            "testStatus": "NOT_TESTED",
            "lastTestAt": None,
            "lastTestMessage": "旧版配置，请保存为新版数据资源后再校验。",
            "legacyResourceType": legacy_type,
            "updatedAt": item.updated_at,
        }

    def _decrypt_config(self, item: CompanyResourceConfig | None) -> dict[str, Any]:
        if not item or not item.config_encrypted:
            return {}
        try:
            data = json.loads(decrypt_secret(item.config_encrypted))
            if isinstance(data, dict) and "config" in data and isinstance(data.get("config"), dict):
                return data.get("config") or {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _merge_preserved_secrets(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        result = dict(incoming or {})
        for key, value in list(result.items()):
            if value == SECRET_PLACEHOLDER and key in existing:
                result[key] = existing[key]
        return result

    def _ensure_project(self, company_id: int, project_id: int) -> CrawlerProject:
        project = self.db.get(CrawlerProject, project_id)
        if not project or project.company_id != company_id:
            raise AppError("项目不存在或不属于当前公司", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        return project
