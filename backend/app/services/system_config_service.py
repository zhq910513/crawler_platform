from __future__ import annotations

from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen

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
        preflight = self.inspect_control_plane_preflight(value, detected_base_url)
        return {
            "controlPlanePublicBaseUrl": value,
            "controlPlanePublicBaseUrlSource": resolved["source"],
            "controlPlanePublicBaseUrlConfigured": bool(value),
            "controlPlanePublicBaseUrlWarnings": resolved["warnings"],
            "controlPlanePreflight": preflight,
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

    def inspect_control_plane_preflight(self, control_plane_url: str = "", detected_base_url: str = "") -> dict:
        base = (control_plane_url or self.resolve_control_plane_public_base_url(detected_base_url) or "").strip().rstrip("/")
        checks: list[dict] = []
        required_ports: list[dict] = []

        def add_check(key: str, label: str, status_value: str, message: str, blocking: bool = False, suggestion: str = "", details: dict | None = None) -> None:
            checks.append({
                "key": key,
                "label": label,
                "status": status_value,
                "message": message,
                "blocking": bool(blocking),
                "suggestion": suggestion,
                "details": details or {},
            })

        parsed = urlparse(base) if base else None
        if not base:
            add_check("control_plane_url", "控制端访问地址", "FAIL", "未配置控制端公网回调地址，执行节点无法知道要连接哪里。", True, "到系统设置填写当前平台的公网 IP、域名或带端口地址。")
        elif parsed and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            add_check("control_plane_url", "控制端访问地址", "FAIL", "控制端公网回调地址格式不正确。", True, "地址必须以 http:// 或 https:// 开头。", {"value": base})
        else:
            assert parsed is not None
            host = (parsed.hostname or "").lower()
            port = parsed.port or (80 if parsed.scheme == "http" else 443)
            required_ports.append({"name": "平台访问入口", "host": host, "port": port, "protocol": "TCP", "reason": "执行节点下载安装脚本、调用 /health、上报心跳和领取任务。"})
            if host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
                add_check("control_plane_public_host", "公网地址可用性", "FAIL", "当前地址是本机地址，远程执行节点无法访问。", True, "改成执行节点能访问的公网 IP、域名或内网互通地址。", {"host": host})
            elif self._is_private_host(host):
                add_check("control_plane_public_host", "公网地址可用性", "WARN", "当前地址看起来是内网地址，只有同一内网/VPN 内的执行节点才能访问。", False, "如果执行节点不在同一网络，请改成公网 IP 或域名。", {"host": host})
            else:
                add_check("control_plane_public_host", "公网地址可用性", "PASS", "控制端地址不是本机回环地址。", False, "", {"host": host})

            health = self._http_probe(f"{base}/health")
            add_check("control_plane_health", "平台健康接口", "PASS" if health["ok"] else "FAIL", "控制端 /health 可访问。" if health["ok"] else f"控制端 /health 当前不可访问：{health['message']}", not health["ok"], "检查平台服务器安全组/防火墙是否放行该端口，确认 docker compose 端口映射和 Web 容器正常。", health)
            installer = self._http_probe(f"{base}/api/v1/agent-installers/linux.sh")
            add_check("agent_installer", "安装脚本地址", "PASS" if installer["ok"] else "FAIL", "Agent 安装脚本可下载。" if installer["ok"] else f"Agent 安装脚本不可下载：{installer['message']}", not installer["ok"], "确认 /api/v1/agent-installers/linux.sh 能通过控制端公网地址访问。", installer)

        image = str(settings.crawler_agent_image or "").strip()
        if not image:
            add_check("agent_image", "Agent 镜像地址", "FAIL", "未配置 Agent 镜像地址。", True, "配置 CRAWLER_AGENT_IMAGE。")
        elif not self._image_has_registry_prefix(image):
            add_check("agent_image", "Agent 镜像地址", "FAIL", f"Agent 镜像未配置私有仓库前缀：{image}。远程节点会默认从 Docker Hub 拉取，通常无法拉到私有镜像。", True, "将 CRAWLER_AGENT_IMAGE 改成执行节点可访问的完整镜像地址，例如 42.193.226.138:5000/crawler_platform_agent:版本。", {"image": image})
        else:
            registry = image.split('/', 1)[0]
            registry_host = registry.rsplit(':', 1)[0] if ':' in registry else registry
            registry_port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
            required_ports.append({"name": "Agent 镜像仓库", "host": registry_host, "port": registry_port, "protocol": "TCP", "reason": "执行节点需要从这里拉取 crawler_platform_agent 镜像。"})
            registry_probe = self._registry_probe(registry)
            add_check("agent_registry", "Agent 镜像仓库", "PASS" if registry_probe["ok"] else "FAIL", f"Agent 镜像仓库可访问：{registry}" if registry_probe["ok"] else f"Agent 镜像仓库当前不可访问：{registry_probe['message']}", not registry_probe["ok"], "检查爬虫平台服务器安全组/防火墙是否向执行节点放行镜像仓库端口；HTTP registry 还需要在执行节点 Docker 配置 insecure-registries。", {**registry_probe, "image": image, "registry": registry})

        blocking_count = sum(1 for item in checks if item["blocking"] and item["status"] == "FAIL")
        warning_count = sum(1 for item in checks if item["status"] == "WARN")
        return {
            "readyForRemoteAgent": blocking_count == 0,
            "status": "PASS" if blocking_count == 0 and warning_count == 0 else ("WARN" if blocking_count == 0 else "FAIL"),
            "summary": "控制端对外连通条件已具备。" if blocking_count == 0 else f"控制端还有 {blocking_count} 个阻断项，执行节点接入大概率会失败。",
            "blockingCount": blocking_count,
            "warningCount": warning_count,
            "checks": checks,
            "requiredPorts": required_ports,
            "agentImage": image,
        }

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
    def _http_probe(url: str, timeout: float = 1.0) -> dict:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() == "testserver":
            return {"ok": True, "statusCode": 200, "url": url, "message": "TestClient virtual origin"}
        try:
            req = UrlRequest(url, headers={"User-Agent": "crawler-platform-preflight/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                status_code = int(getattr(resp, "status", 0) or 0)
                return {"ok": 200 <= status_code < 500, "statusCode": status_code, "url": url, "message": f"HTTP {status_code}"}
        except HTTPError as exc:
            return {"ok": exc.code < 500, "statusCode": exc.code, "url": url, "message": f"HTTP {exc.code}"}
        except URLError as exc:
            return {"ok": False, "statusCode": 0, "url": url, "message": str(getattr(exc, "reason", exc))}
        except Exception as exc:  # pragma: no cover - defensive probe guard
            return {"ok": False, "statusCode": 0, "url": url, "message": str(exc)}

    def _registry_probe(self, registry: str) -> dict:
        host = registry.rsplit(':', 1)[0] if ':' in registry else registry
        port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
        schemes = ["http", "https"] if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else ["https", "http"]
        attempts = []
        for scheme in schemes:
            probe = self._http_probe(f"{scheme}://{registry}/v2/", timeout=1.0)
            attempts.append(probe)
            if probe["ok"]:
                return {**probe, "attempts": attempts}
        return {"ok": False, "statusCode": 0, "url": attempts[-1]["url"] if attempts else "", "message": "; ".join(item["message"] for item in attempts) or "无法访问镜像仓库", "attempts": attempts}

    @staticmethod
    def _image_has_registry_prefix(image: str) -> bool:
        first = (image or "").split("/", 1)[0]
        if not first or first == image:
            return False
        return "." in first or ":" in first or first == "localhost"

    @staticmethod
    def _is_private_host(host: str) -> bool:
        if host.startswith("192.168.") or host.startswith("10."):
            return True
        if host.startswith("172."):
            parts = host.split(".")
            return len(parts) > 1 and parts[1].isdigit() and 16 <= int(parts[1]) <= 31
        return False

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
