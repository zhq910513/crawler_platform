from __future__ import annotations

from urllib.parse import urlparse

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import SysConfig, SysUser
from app.schemas import SystemSettingsUpdate
from app.services.audit import write_operation_log
from app.services.permissions import require_super_admin
from app.config import settings

PLATFORM_PUBLIC_URL_KEY = "platform.public_url"


class SystemConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_system_settings(self) -> dict:
        value = self._get_value(PLATFORM_PUBLIC_URL_KEY)
        if value:
            source = "SYSTEM_SETTING"
        elif settings.platform_public_url:
            value = settings.platform_public_url
            source = "ENV"
        else:
            value = ""
            source = "EMPTY"
        return {
            "platformPublicUrl": value,
            "platformPublicUrlSource": source,
            "platformPublicUrlConfigured": bool(value),
        }

    def update_system_settings(self, user: SysUser, payload: SystemSettingsUpdate) -> dict:
        require_super_admin(user)
        if payload.platform_public_url is not None:
            value = payload.platform_public_url.strip().rstrip("/")
            if value:
                self._validate_url(value)
            before = {"platformPublicUrl": self._get_value(PLATFORM_PUBLIC_URL_KEY)}
            self._set_value(PLATFORM_PUBLIC_URL_KEY, "平台访问地址", value, "Agent、执行节点和外部流水线访问平台时使用的地址")
            after = {"platformPublicUrl": value}
            write_operation_log(self.db, user, None, operation_type="UPDATE_SYSTEM_SETTINGS", resource_type="system_settings", resource_id="platform_public_url", before_data=before, after_data=after)
            self.db.commit()
        return self.get_system_settings()

    def resolve_platform_public_url(self) -> str:
        return (self._get_value(PLATFORM_PUBLIC_URL_KEY) or settings.platform_public_url or "").strip().rstrip("/")

    def _get_value(self, key: str) -> str:
        item = self.db.scalar(select(SysConfig).where(SysConfig.config_key == key))
        return (item.config_value if item else "") or ""

    def _set_value(self, key: str, name: str, value: str, description: str) -> SysConfig:
        item = self.db.scalar(select(SysConfig).where(SysConfig.config_key == key))
        if not item:
            item = SysConfig(config_key=key, config_name=name, config_value=value, description=description)
            self.db.add(item)
        else:
            item.config_name = name
            item.config_value = value
            item.description = description
        self.db.flush()
        return item

    @staticmethod
    def _validate_url(value: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError("平台访问地址必须以 http:// 或 https:// 开头", code=40072, http_status=status.HTTP_400_BAD_REQUEST)
