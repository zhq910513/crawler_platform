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
        }

    def update_system_settings(self, user: SysUser, payload: SystemSettingsUpdate) -> dict:
        require_super_admin(user)
        raw_value = payload.control_plane_public_base_url
        if raw_value is not None:
            value = raw_value.strip().rstrip("/")
            if value:
                self._validate_url(value, "控制端公网回调地址")
            before = {"controlPlanePublicBaseUrl": self._get_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY)}
            self._set_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY, "控制端公网回调地址", value, "代码构建流程和外部执行节点访问控制端服务使用的公网地址")
            after = {"controlPlanePublicBaseUrl": value}
            write_operation_log(self.db, user, None, operation_type="UPDATE_SYSTEM_SETTINGS", resource_type="system_settings", resource_id="control_plane_public_base_url", before_data=before, after_data=after)
            self.db.commit()
        return self.get_system_settings()

    def resolve_control_plane_public_base_url(self, detected_base_url: str = "") -> str:
        return self.inspect_control_plane_public_base_url(detected_base_url)["controlPlanePublicBaseUrl"]

    def inspect_control_plane_public_base_url(self, detected_base_url: str = "") -> dict:
        detected = (detected_base_url or "").strip().rstrip("/")
        candidates = [
            ("SYSTEM_SETTING", self._get_value(CONTROL_PLANE_PUBLIC_BASE_URL_KEY)),
            ("ENV", settings.control_plane_public_base_url),
            ("DETECTED_ORIGIN", detected),
        ]
        for source, value in candidates:
            cleaned = (value or "").strip().rstrip("/")
            if not cleaned:
                continue
            parsed = urlparse(cleaned)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                resolved, source_suffix, port_warning = self._prefer_detected_origin_port(cleaned, detected)
                warnings = self._url_warnings(urlparse(resolved))
                if port_warning:
                    warnings.append(port_warning)
                return {"controlPlanePublicBaseUrl": resolved, "source": source + source_suffix, "warnings": warnings}
        return {"controlPlanePublicBaseUrl": "", "source": "EMPTY", "warnings": []}

    @staticmethod
    def detected_base_url_from_request(request: Request) -> str:
        forwarded_host = (request.headers.get("x-forwarded-host") or "").split(",", 1)[0].strip()
        host = forwarded_host or request.headers.get("host") or request.url.netloc
        forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip()
        proto = forwarded_proto or request.url.scheme
        if not host:
            return ""
        return f"{proto}://{host}".rstrip("/")


    @staticmethod
    def _prefer_detected_origin_port(configured_url: str, detected_url: str) -> tuple[str, str, str]:
        if not detected_url:
            return configured_url, "", ""
        configured = urlparse(configured_url)
        detected = urlparse(detected_url)
        if configured.scheme not in {"http", "https"} or detected.scheme not in {"http", "https"}:
            return configured_url, "", ""
        if not configured.hostname or not detected.hostname:
            return configured_url, "", ""
        same_origin_host = configured.scheme == detected.scheme and configured.hostname.lower() == detected.hostname.lower()
        if not same_origin_host:
            return configured_url, "", ""
        detected_has_explicit_non_default_port = detected.port is not None and detected.port != (80 if detected.scheme == "http" else 443)
        configured_missing_port = configured.port is None
        if configured_missing_port and detected_has_explicit_non_default_port:
            warning = f"配置地址未带端口，已按当前访问入口临时使用 {detected_url} 生成外部接入命令；请到系统设置保存完整地址。"
            return detected_url, "+DETECTED_PORT", warning
        return configured_url, "", ""

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
            return ["该地址是本机地址，GitHub Actions 和远程执行节点通常无法访问。"]
        if host.startswith("192.168.") or host.startswith("10."):
            return ["该地址看起来是内网地址，GitHub Actions 可能无法访问。"]
        if host.startswith("172."):
            parts = host.split(".")
            if len(parts) > 1 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31:
                return ["该地址看起来是内网地址，GitHub Actions 可能无法访问。"]
        return []
