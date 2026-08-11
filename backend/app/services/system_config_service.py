from __future__ import annotations

from urllib.parse import urlparse

from fastapi import Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import SysConfig, SysUser
from app.schemas import SystemSettingsUpdate
from app.services.audit import write_operation_log
from app.services.permissions import require_super_admin

CONTROL_PLANE_PUBLIC_BASE_URL_KEY = "control_plane.public_base_url"
PLATFORM_PUBLIC_URL_KEY = "platform.public_url"


class SystemConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_system_settings(self, detected_base_url: str = "") -> dict:
        resolved = self.inspect_control_plane_public_base_url(detected_base_url)
        value = resolved["controlPlanePublicBaseUrl"]
        return {
            "controlPlanePublicBaseUrl": value,
            "controlPlanePublicBaseUrlSource": resolved["source"],
            "controlPlanePublicBaseUrlConfigured": bool(value),
            "controlPlanePublicBaseUrlWarnings": resolved["warnings"],
            # 旧字段保留给前端/脚本兼容；新文案不再使用“平台访问地址”。
            "platformPublicUrl": value,
            "platformPublicUrlSource": resolved["source"],
            "platformPublicUrlConfigured": bool(value),
        }

    def update_system_settings(self, user: SysUser, payload: SystemSettingsUpdate) -> dict:
        require_super_admin(user)
        raw_value = payload.control_plane_public_base_url
        if raw_value is None:
            raw_value = payload.platform_public_url
        if raw_value is not None:
            value = raw_value.strip().rstrip("/")
            if value:
                self._validate_url(value, "控制端公网回调地址")
            before = {"controlPlanePublicBaseUrl": self._get_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY) or self._get_value(PLATFORM_PUBLIC_URL_KEY)}
            self._set_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY, "控制端公网回调地址", value, "Git CI、Agent 和外部执行节点访问控制端 API 时使用的公网地址")
            # 同步旧 key，避免旧安装脚本/旧页面读取不到。
            self._set_value(PLATFORM_PUBLIC_URL_KEY, "控制端公网回调地址", value, "兼容旧配置项；新代码优先读取 control_plane.public_base_url")
            after = {"controlPlanePublicBaseUrl": value}
            write_operation_log(self.db, user, None, operation_type="UPDATE_SYSTEM_SETTINGS", resource_type="system_settings", resource_id="control_plane_public_base_url", before_data=before, after_data=after)
            self.db.commit()
        return self.get_system_settings()

    def resolve_control_plane_public_base_url(self, detected_base_url: str = "") -> str:
        return self.inspect_control_plane_public_base_url(detected_base_url)["controlPlanePublicBaseUrl"]

    def inspect_control_plane_public_base_url(self, detected_base_url: str = "") -> dict:
        candidates = [
            ("SYSTEM_SETTING", self._get_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY)),
            ("LEGACY_SYSTEM_SETTING", self._get_value(PLATFORM_PUBLIC_URL_KEY)),
            ("ENV", settings.control_plane_public_base_url),
            ("LEGACY_ENV", settings.platform_public_url),
            ("DETECTED_ORIGIN", detected_base_url),
        ]
        for source, value in candidates:
            cleaned = (value or "").strip().rstrip("/")
            if not cleaned:
                continue
            parsed = urlparse(cleaned)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                warnings = self._url_warnings(parsed)
                return {"controlPlanePublicBaseUrl": cleaned, "source": source, "warnings": warnings}
        return {"controlPlanePublicBaseUrl": "", "source": "EMPTY", "warnings": []}

    # 旧方法名保留，避免 server/agent 接入链路大范围改名带来风险。
    def resolve_platform_public_url(self) -> str:
        return self.resolve_control_plane_public_base_url()

    @staticmethod
    def detected_base_url_from_request(request: Request) -> str:
        forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()
        host = forwarded_host or request.headers.get("host") or request.url.netloc
        forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
        proto = forwarded_proto or request.url.scheme
        if not host:
            return ""
        return f"{proto}://{host}".rstrip("/")

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
    def _validate_url(value: str, field_name: str = "URL") -> None:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError(f"{field_name}必须以 http:// 或 https:// 开头", code=40072, http_status=status.HTTP_400_BAD_REQUEST)

    @staticmethod
    def _url_warnings(parsed) -> list[str]:
        host = (parsed.hostname or "").lower()
        if host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
            return ["该地址是本机地址，GitHub Actions 和远程 Agent 通常无法访问。"]
        if host.startswith("192.168.") or host.startswith("10."):
            return ["该地址看起来是内网地址，GitHub Actions 可能无法访问。"]
        if host.startswith("172."):
            parts = host.split(".")
            if len(parts) > 1 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return ["该地址看起来是内网地址，GitHub Actions 可能无法访问。"]
        return []
