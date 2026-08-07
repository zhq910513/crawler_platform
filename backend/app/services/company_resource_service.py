from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import CrawlerCompany, SysSecret, SysUser
from app.schemas import CompanyResourceConfigCreate, CompanyResourceConfigTest
from app.security import decrypt_secret, encrypt_secret
from app.services.audit import write_operation_log
from app.services.permissions import require_company_scope, require_super_admin, scoped_company_id
from app.utils import utcnow

RESOURCE_LABELS = {
    "MYSQL_MAIN": "主业务数据库",
    "REDIS_CACHE": "Cookie 缓存库",
    "MONGO_RAW": "原始数据存储",
    "OSS_MEDIA": "媒体存储",
}

SENSITIVE_KEYS = {"password", "passwd", "pwd", "secret", "token", "access_key_secret", "accessKeySecret", "access_key", "accessKey"}


def _resource_secret_code(company_id: int, resource_type: str) -> str:
    return f"company_resource:{company_id}:{resource_type}"


class CompanyResourceService:
    def __init__(self, db: Session):
        self.db = db

    def list_resources(self, user: SysUser, company_id: int | None = None) -> list[dict]:
        scoped = scoped_company_id(user, company_id)
        if scoped is None:
            raise AppError("请选择公司", code=40081)
        stmt = select(SysSecret).where(SysSecret.company_id == scoped, SysSecret.secret_code.like(f"company_resource:{scoped}:%"), SysSecret.enabled.is_(True)).order_by(SysSecret.updated_at.desc())
        return [self._to_public(item) for item in self.db.scalars(stmt).all()]

    def upsert_resource(self, user: SysUser, payload: CompanyResourceConfigCreate) -> dict:
        require_company_scope(user, payload.company_id)
        if not self.db.get(CrawlerCompany, payload.company_id):
            raise AppError("公司不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        secret_code = _resource_secret_code(payload.company_id, payload.resource_type)
        item = self.db.scalar(select(SysSecret).where(SysSecret.secret_code == secret_code))
        now = utcnow()
        data = {
            "resourceType": payload.resource_type,
            "resourceName": payload.resource_name or RESOURCE_LABELS.get(payload.resource_type, payload.resource_type),
            "config": payload.config,
            "testStatus": "NOT_TESTED",
            "lastTestAt": None,
            "lastTestMessage": "保存成功，尚未测试",
            "updatedAt": now.isoformat(),
        }
        if not item:
            item = SysSecret(company_id=payload.company_id, project_id=None, secret_code=secret_code, secret_name=data["resourceName"], encrypted_value=encrypt_secret(json.dumps(data, ensure_ascii=False)), description="公司运行资源配置", enabled=True)
            self.db.add(item)
        else:
            old = self._decrypt(item)
            data["testStatus"] = old.get("testStatus") or "NOT_TESTED"
            data["lastTestAt"] = old.get("lastTestAt")
            data["lastTestMessage"] = old.get("lastTestMessage") or "保存成功"
            item.secret_name = data["resourceName"]
            item.encrypted_value = encrypt_secret(json.dumps(data, ensure_ascii=False))
            item.enabled = True
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="UPSERT_COMPANY_RESOURCE", resource_type="company_resource", resource_id=str(item.secret_id), after_data={"companyId": payload.company_id, "resourceType": payload.resource_type})
        self.db.commit()
        return self._to_public(item)

    def test_resource(self, user: SysUser, config_id: int, payload: CompanyResourceConfigTest) -> dict:
        item = self.db.get(SysSecret, config_id)
        if not item or not item.company_id or not item.secret_code.startswith(f"company_resource:{item.company_id}:"):
            raise AppError("资源配置不存在", code=40401, http_status=status.HTTP_404_NOT_FOUND)
        require_company_scope(user, item.company_id)
        data = self._decrypt(item)
        status_text, message = self._validate_config(data.get("resourceType") or "", data.get("config") or {})
        if payload.force_success:
            status_text, message = "PASSED", "已人工确认可用"
        data["testStatus"] = status_text
        data["lastTestAt"] = utcnow().isoformat()
        data["lastTestMessage"] = message
        item.encrypted_value = encrypt_secret(json.dumps(data, ensure_ascii=False))
        self.db.flush()
        write_operation_log(self.db, user, None, operation_type="TEST_COMPANY_RESOURCE", resource_type="company_resource", resource_id=str(config_id), after_data={"testStatus": status_text, "message": message})
        self.db.commit()
        return self._to_public(item)

    def _to_public(self, item: SysSecret) -> dict:
        data = self._decrypt(item)
        return {
            "configId": item.secret_id,
            "companyId": item.company_id,
            "resourceType": data.get("resourceType") or item.secret_code.split(":")[-1],
            "resourceLabel": RESOURCE_LABELS.get(data.get("resourceType") or "", data.get("resourceName") or item.secret_name),
            "resourceName": data.get("resourceName") or item.secret_name,
            "testStatus": data.get("testStatus") or "NOT_TESTED",
            "lastTestAt": data.get("lastTestAt"),
            "lastTestMessage": data.get("lastTestMessage") or "",
            "configMasked": self._mask_config(data.get("config") or {}),
            "updatedAt": item.updated_at,
        }

    def _decrypt(self, item: SysSecret) -> dict[str, Any]:
        try:
            return json.loads(decrypt_secret(item.encrypted_value))
        except Exception:
            return {}

    @staticmethod
    def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
        masked: dict[str, Any] = {}
        for key, value in (config or {}).items():
            if any(part in str(key).lower() for part in SENSITIVE_KEYS):
                masked[key] = "******" if value else ""
            else:
                masked[key] = value
        return masked

    @staticmethod
    def _validate_config(resource_type: str, config: dict[str, Any]) -> tuple[str, str]:
        if resource_type == "MYSQL_MAIN":
            required = ["host", "port", "database", "username"]
        elif resource_type == "REDIS_CACHE":
            required = ["host", "port"]
        elif resource_type == "MONGO_RAW":
            required = ["uri"] if config.get("uri") else ["host", "port", "database"]
        elif resource_type == "OSS_MEDIA":
            required = ["endpoint", "bucket"]
        else:
            required = []
        missing = [item for item in required if not str(config.get(item) or "").strip()]
        if missing:
            return "FAILED", "缺少必要配置：" + "、".join(missing)
        return "PASSED", "基础配置完整，已标记为测试通过"
