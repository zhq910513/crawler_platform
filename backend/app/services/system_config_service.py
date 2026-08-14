from __future__ import annotations

from urllib.error import HTTPError, URLError
import json
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
from app.utils import utcnow

CONTROL_PLANE_PUBLIC_BASE_URL_KEY = "control_plane.public_base_url"


class SystemConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_system_settings(self, detected_base_url: str = "", check_source: str = "AUTO") -> dict:
        resolved = self.inspect_control_plane_public_base_url(detected_base_url)
        value = resolved["controlPlanePublicBaseUrl"]
        preflight = self.inspect_control_plane_preflight(value, detected_base_url, check_source=check_source)
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

    def inspect_control_plane_preflight(self, control_plane_url: str = "", detected_base_url: str = "", check_source: str = "AUTO") -> dict:
        base = (control_plane_url or self.resolve_control_plane_public_base_url(detected_base_url) or "").strip().rstrip("/")
        checks: list[dict] = []
        required_ports: list[dict] = []
        checked_at = utcnow().isoformat()
        source_key = (check_source or "AUTO").strip().upper()
        if source_key == "MANUAL":
            source_label = "手动检测"
        elif source_key in {"DEPLOY", "BOOTSTRAP", "REDEPLOY"}:
            source_label = "部署后自动检测"
        else:
            source_key = "AUTO"
            source_label = "页面自动检测"

        def add_check(
            key: str,
            label: str,
            status_value: str,
            message: str,
            blocking: bool = False,
            suggestion: str = "",
            details: dict | None = None,
            action: str = "",
            verify_command: str = "",
            impact: str = "",
            route: str = "",
            action_label: str = "去处理",
            category: str = "平台接入",
            can_ignore: bool = False,
            automation_type: str = "MANUAL",
            handler: str = "操作员",
            auto_action_command: str = "",
        ) -> None:
            checks.append({
                "key": key,
                "label": label,
                "status": status_value,
                "message": message,
                "blocking": bool(blocking),
                "suggestion": suggestion,
                "action": action or suggestion,
                "verifyCommand": verify_command,
                "impact": impact or "影响执行节点接入链路。",
                "route": route,
                "actionLabel": action_label,
                "category": category,
                "canIgnore": bool(can_ignore),
                "automationType": automation_type,
                "handler": handler,
                "autoActionCommand": auto_action_command,
                "details": details or {},
            })

        parsed = urlparse(base) if base else None
        if not base:
            add_check(
                "control_plane_url",
                "控制端访问地址",
                "FAIL",
                "未配置控制端公网地址，执行节点不知道要连接哪台平台服务器。",
                True,
                "到系统设置填写当前平台的公网 IP、域名或带端口地址，保存后回到运行总览点击重新检测。",
                action="操作员进入 系统设置 -> 基础配置，填写控制端公网地址，例如 http://42.193.226.138:8080。",
                impact="远程执行节点无法下载安装脚本、上报心跳或领取任务；新增远程节点会失败。",
                route="/settings?focus=controlPlaneUrl",
                action_label="去系统设置配置",
                category="平台访问入口",
            )
        elif parsed and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            add_check(
                "control_plane_url",
                "控制端访问地址",
                "FAIL",
                "控制端公网地址格式不正确。",
                True,
                "地址必须以 http:// 或 https:// 开头，保存后回到运行总览点击重新检测。",
                {"value": base},
                action="操作员把控制端公网地址改成 http://公网IP:端口 或 https://域名。",
                impact="安装脚本和 Agent 无法识别控制端地址；远程节点接入会失败。",
                route="/settings?focus=controlPlaneUrl",
                action_label="修正地址格式",
                category="平台访问入口",
            )
        else:
            assert parsed is not None
            host = (parsed.hostname or "").lower()
            port = parsed.port or (80 if parsed.scheme == "http" else 443)
            health_command = f"curl -fsSL {base}/health && echo"
            installer_command = f"curl -fsSL {base}/api/v1/agent-installers/linux.sh | head -5"
            required_ports.append({
                "name": "平台访问入口",
                "host": host,
                "port": port,
                "protocol": "TCP",
                "reason": "执行节点下载安装脚本、调用 /health、上报心跳和领取任务。",
                "impact": "执行节点需要通过这个入口下载安装脚本、上报心跳和领取任务。",
                "action": f"在云防火墙/安全组放行 {port}/TCP，来源建议限制为执行节点公网 IP；处理后点击运行总览的重新检测。",
                "actionLabel": "放行平台入口端口",
                "verifyCommand": health_command,
                "automationType": "CLOUD_CONSOLE",
                "handler": "云控制台",
            })
            if host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
                add_check(
                    "control_plane_public_host",
                    "公网地址可用性",
                    "FAIL",
                    "当前地址是本机地址，远程执行节点无法访问。",
                    True,
                    "改成执行节点能访问的公网 IP、域名或内网互通地址，保存后重新检测。",
                    {"host": host},
                    action="操作员进入 系统设置 -> 基础配置，把地址改成执行节点能访问的平台地址。",
                    impact="远程执行节点会把 127.0.0.1 当成自己本机，无法连到平台。",
                    route="/settings?focus=controlPlaneUrl",
                    action_label="改成公网或内网互通地址",
                    category="平台访问入口",
                )
            elif self._is_private_host(host):
                add_check(
                    "control_plane_public_host",
                    "公网地址可用性",
                    "WARN",
                    "当前地址看起来是内网地址，只有同一内网/VPN 内的执行节点才能访问。",
                    False,
                    "如果执行节点不在同一网络，请改成公网 IP 或域名；如果在同一内网，请在执行节点执行验证命令确认。",
                    {"host": host},
                    action=f"操作员在目标执行节点执行：{health_command}",
                    verify_command=health_command,
                    impact="如果执行节点不在同一内网/VPN，会无法下载脚本和上报心跳。",
                    route="/settings?focus=controlPlaneUrl",
                    action_label="在节点验证连通性",
                    category="平台访问入口",
                    can_ignore=True,
                )
            else:
                add_check("control_plane_public_host", "公网地址可用性", "PASS", "控制端地址不是本机回环地址。", False, "", {"host": host}, impact="远程节点可以使用该地址作为控制端入口。", category="平台访问入口")

            health = self._http_probe(f"{base}/health")
            add_check(
                "control_plane_health",
                "平台健康接口",
                "PASS" if health["ok"] else "WARN",
                "控制端 /health 可访问。" if health["ok"] else f"控制端本机未能确认 /health 可访问：{health['message']}。这可能是云服务器 NAT 回环或容器网络限制，不代表执行节点一定不可访问。",
                False,
                "请在目标执行节点执行连通性验证命令；如果失败，再检查平台服务器安全组、防火墙、端口映射和 Web 容器。",
                health,
                action=f"操作员在目标执行节点执行：{health_command}；失败时放行平台入口端口并确认 docker compose 端口映射。",
                verify_command=health_command,
                impact="如果该验证在目标节点失败，Agent 后续心跳、领取任务都会失败。",
                action_label="在节点验证 /health",
                category="平台访问入口",
                can_ignore=True,
            )
            installer = self._http_probe(f"{base}/api/v1/agent-installers/linux.sh")
            add_check(
                "agent_installer",
                "安装脚本地址",
                "PASS" if installer["ok"] else "WARN",
                "Agent 安装脚本可下载。" if installer["ok"] else f"控制端本机未能确认安装脚本可下载：{installer['message']}。请以执行节点外部验证结果为准。",
                False,
                "请在目标执行节点执行安装脚本下载验证命令；如果失败，再检查 /api/v1/agent-installers/linux.sh 是否能通过控制端公网地址访问。",
                installer,
                action=f"操作员在目标执行节点执行：{installer_command}；失败时检查平台入口端口、安全组和 Web/API 反向代理。",
                verify_command=installer_command,
                impact="安装脚本不可下载时，执行节点无法完成自动接入。",
                action_label="在节点验证安装脚本",
                category="平台访问入口",
                can_ignore=True,
            )

        image = str(settings.crawler_agent_image or "").strip()
        if not image:
            add_check(
                "agent_image",
                "Agent 镜像地址",
                "FAIL",
                "未配置 Agent 镜像地址，执行节点无法拉取 Agent 容器。",
                True,
                "配置 CRAWLER_AGENT_IMAGE 后重启 API/Scheduler/Maintenance，再回到运行总览点击重新检测。",
                action="平台可自动处理：在平台服务器执行 bash deploy/scripts/prepare-agent-image.sh，脚本会构建 Agent 镜像、推送到内置 registry、写入 CRAWLER_AGENT_IMAGE 并重启后端服务。",
                impact="远程执行节点无法拉取 Agent 容器，新增节点无法启动；已在线节点不受影响。",
                route="/dashboard?focus=platformPreflight",
                action_label="准备 Agent 镜像",
                category="Agent 镜像分发",
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command="bash deploy/scripts/prepare-agent-image.sh",
            )
        elif not self._image_has_registry_prefix(image):
            add_check(
                "agent_image",
                "Agent 镜像地址",
                "FAIL",
                f"Agent 镜像未配置私有仓库前缀：{image}。远程节点会默认从 Docker Hub 拉取，通常无法拉到你的私有镜像。",
                True,
                "将 CRAWLER_AGENT_IMAGE 改成执行节点可访问的完整镜像地址，例如 42.193.226.138:5000/crawler_platform_agent:版本。",
                {"image": image},
                action="平台可自动处理：在平台服务器执行 bash deploy/scripts/prepare-agent-image.sh，脚本会自动构建、tag、push Agent 镜像，写入 CRAWLER_AGENT_IMAGE=公网IP:5000/crawler_platform_agent:版本 并重启后端服务。",
                impact="远程节点会默认去 Docker Hub 拉你的私有镜像，通常会拉取失败；已在线节点不受影响。",
                route="/dashboard?focus=platformPreflight",
                action_label="自动准备镜像分发",
                category="Agent 镜像分发",
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command="bash deploy/scripts/prepare-agent-image.sh",
            )
        else:
            registry = image.split('/', 1)[0]
            registry_host = registry.rsplit(':', 1)[0] if ':' in registry else registry
            registry_port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
            scheme_hint = "http" if registry_port in {5000, 80} or registry_host in {"localhost", "127.0.0.1"} else "https"
            registry_command = f"curl -i {scheme_hint}://{registry}/v2/"
            pull_command = f"docker pull {image}"
            required_ports.append({
                "name": "Agent 镜像仓库",
                "host": registry_host,
                "port": registry_port,
                "protocol": "TCP",
                "reason": "执行节点需要从这里拉取 crawler_platform_agent 镜像。",
                "impact": "远程执行节点需要访问该仓库拉取 Agent 镜像。",
                "action": f"在镜像仓库所在服务器放行 {registry_port}/TCP，来源建议限制为执行节点公网 IP；HTTP registry 还要在执行节点 Docker 配置 insecure-registries。",
                "actionLabel": "放行镜像仓库端口",
                "verifyCommand": registry_command,
                "automationType": "CLOUD_CONSOLE",
                "handler": "云控制台",
            })
            registry_probe = self._registry_probe(registry)
            add_check(
                "agent_registry",
                "Agent 镜像仓库",
                "PASS" if registry_probe["ok"] else "WARN",
                f"Agent 镜像仓库可访问：{registry}" if registry_probe["ok"] else f"控制端本机未能确认 Agent 镜像仓库可访问：{registry_probe['message']}。请在执行节点验证仓库端口和镜像拉取。",
                False,
                "在执行节点验证镜像仓库 /v2/ 和 docker pull；如果失败，放行仓库端口，HTTP registry 需要配置 insecure-registries。",
                {**registry_probe, "image": image, "registry": registry},
                action=f"操作员先在云安全组放行 {registry_port}/TCP；执行节点安装脚本可在授权后自动配置 Docker insecure-registries，安装命令追加 --auto-configure-docker-registry。",
                verify_command=registry_command,
                impact="镜像仓库不可达时，远程执行节点无法启动 Agent 容器；已在线节点不受影响。",
                action_label="验证镜像仓库",
                category="Agent 镜像分发",
                can_ignore=True,
                automation_type="NODE_INSTALLER_AUTHORIZED",
                handler="执行节点安装脚本",
                auto_action_command="在执行节点安装命令后追加 --auto-configure-docker-registry",
            )
            tag_probe = self._registry_tag_probe(image)
            add_check(
                "agent_image_tag",
                "Agent 镜像版本",
                "PASS" if tag_probe["ok"] else "WARN",
                f"Agent 镜像 tag 可查询：{image}" if tag_probe["ok"] else f"控制端本机未能确认 Agent 镜像 tag 已推送：{tag_probe['message']}。请在执行节点或平台服务器验证 docker pull。",
                False,
                "使用平台脚本准备镜像，或在执行节点执行 docker pull 验证镜像是否可拉取。",
                tag_probe,
                action=f"平台可自动处理：执行 bash deploy/scripts/prepare-agent-image.sh；处理后验证：{pull_command}",
                verify_command=pull_command,
                impact="镜像仓库存在但 tag 未推送时，执行节点仍会在拉取 Agent 镜像阶段失败。",
                action_label="准备 Agent 镜像 tag",
                category="Agent 镜像分发",
                can_ignore=True,
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command="bash deploy/scripts/prepare-agent-image.sh",
            )

        blocking_count = sum(1 for item in checks if item["blocking"] and item["status"] == "FAIL")
        warning_count = sum(1 for item in checks if item["status"] == "WARN")
        if blocking_count:
            summary = f"平台自检发现 {blocking_count} 个必须处理项，按提示处理后点击重新检测。"
        elif warning_count:
            summary = f"平台自检有 {warning_count} 个需确认项，请按提示在执行节点验证；确认通过后可以继续接入。"
        else:
            summary = "平台自检通过，执行节点接入基础条件已具备。"
        next_action = ""
        for item in checks:
            if item["status"] != "PASS":
                next_action = item.get("action") or item.get("suggestion") or "按提示处理后重新检测。"
                break
        return {
            "readyForRemoteAgent": blocking_count == 0,
            "status": "PASS" if blocking_count == 0 and warning_count == 0 else ("WARN" if blocking_count == 0 else "FAIL"),
            "summary": summary,
            "blockingCount": blocking_count,
            "warningCount": warning_count,
            "checks": checks,
            "requiredPorts": required_ports,
            "agentImage": image,
            "checkedAt": checked_at,
            "checkSource": source_key,
            "checkSourceLabel": source_label,
            "nextAction": next_action,
            "automationSummary": self._automation_summary(checks),
        }

    @staticmethod
    def _automation_summary(checks: list[dict]) -> dict:
        summary = {"platformScript": 0, "nodeInstallerAuthorized": 0, "cloudConsole": 0, "manual": 0}
        for item in checks:
            if item.get("status") == "PASS":
                continue
            kind = str(item.get("automationType") or "MANUAL")
            if kind == "PLATFORM_SCRIPT":
                summary["platformScript"] += 1
            elif kind == "NODE_INSTALLER_AUTHORIZED":
                summary["nodeInstallerAuthorized"] += 1
            elif kind == "CLOUD_CONSOLE":
                summary["cloudConsole"] += 1
            else:
                summary["manual"] += 1
        return summary

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

    @staticmethod
    def _http_text_probe(url: str, timeout: float = 1.0) -> dict:
        try:
            req = UrlRequest(url, headers={"User-Agent": "crawler-platform-preflight/1.0"})
            with urlopen(req, timeout=timeout) as resp:
                status_code = int(getattr(resp, "status", 0) or 0)
                body = resp.read(65536).decode("utf-8", errors="replace")
                return {"ok": 200 <= status_code < 500, "statusCode": status_code, "url": url, "message": f"HTTP {status_code}", "body": body}
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read(65536).decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {"ok": exc.code < 500, "statusCode": exc.code, "url": url, "message": f"HTTP {exc.code}", "body": body}
        except URLError as exc:
            return {"ok": False, "statusCode": 0, "url": url, "message": str(getattr(exc, "reason", exc)), "body": ""}
        except Exception as exc:  # pragma: no cover
            return {"ok": False, "statusCode": 0, "url": url, "message": str(exc), "body": ""}

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

    def _registry_tag_probe(self, image: str) -> dict:
        try:
            registry, rest = image.split('/', 1)
            if ':' in rest.rsplit('/', 1)[-1]:
                repo, tag = rest.rsplit(':', 1)
            else:
                repo, tag = rest, 'latest'
        except ValueError:
            return {"ok": False, "message": "镜像地址缺少仓库前缀", "image": image}
        host = registry.rsplit(':', 1)[0] if ':' in registry else registry
        port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
        schemes = ["http", "https"] if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else ["https", "http"]
        attempts = []
        for scheme in schemes:
            url = f"{scheme}://{registry}/v2/{repo}/tags/list"
            probe = self._http_text_probe(url, timeout=1.0)
            attempts.append(probe)
            if probe["ok"]:
                try:
                    payload = json.loads(str(probe.get("body") or "{}"))
                except json.JSONDecodeError:
                    payload = {}
                tags = payload.get("tags") if isinstance(payload, dict) else None
                if isinstance(tags, list) and tag in tags:
                    return {**probe, "image": image, "registry": registry, "repository": repo, "tag": tag, "tags": tags, "attempts": attempts}
                return {**probe, "ok": False, "message": f"仓库可访问，但未找到 tag {tag}", "image": image, "registry": registry, "repository": repo, "tag": tag, "tags": tags or [], "attempts": attempts}
        return {"ok": False, "message": "; ".join(item["message"] for item in attempts) or "无法查询镜像 tag", "image": image, "registry": registry, "attempts": attempts}

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
