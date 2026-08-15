from __future__ import annotations

from urllib.error import HTTPError, URLError
import json
import os
from pathlib import Path
import shlex
import shutil
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.errors import AppError
from app.models import PlatformPreflightSnapshot, SysConfig, SysUser
from app.schemas import SystemSettingsUpdate
from app.services.audit import write_operation_log
from app.services.permissions import require_super_admin
from app.utils import utcnow

CONTROL_PLANE_PUBLIC_BASE_URL_KEY = "control_plane.public_base_url"


class SystemConfigService:
    def __init__(self, db: Session):
        self.db = db

    def get_system_settings(self, detected_base_url: str = "", check_source: str = "AUTO", user: SysUser | None = None, persist_snapshot: bool = False) -> dict:
        resolved = self.inspect_control_plane_public_base_url(detected_base_url)
        value = resolved["controlPlanePublicBaseUrl"]
        preflight = self.inspect_control_plane_preflight(value, detected_base_url, check_source=check_source)
        if persist_snapshot:
            snapshot = self.save_preflight_snapshot(preflight, user)
            preflight["latestSnapshot"] = snapshot
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
        platform_action_capability = self._platform_action_capability_payload()
        prepare_agent_image_command = platform_action_capability["manualCommand"]
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
            action_endpoint: str = "",
            action_button_label: str = "",
            execution_channel: str = "",
            action_available: bool | None = None,
            action_unavailable_reason: str = "",
            manual_command: str = "",
        ) -> None:
            resolved_action_available = bool(action_endpoint) if action_available is None else bool(action_available)
            if automation_type == "PLATFORM_SCRIPT" and action_endpoint:
                resolved_action_available = bool(platform_action_capability.get("available")) if action_available is None else bool(action_available)
                if not resolved_action_available and not action_unavailable_reason:
                    action_unavailable_reason = str(platform_action_capability.get("reason") or "当前页面未启用白名单动作执行能力。")
            resolved_channel = execution_channel or self._execution_channel(automation_type, resolved_action_available)
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
                "actionEndpoint": action_endpoint,
                "actionButtonLabel": action_button_label,
                "actionAvailable": resolved_action_available,
                "actionUnavailableReason": action_unavailable_reason,
                "executionChannel": resolved_channel,
                "manualCommand": manual_command or (prepare_agent_image_command if automation_type == "PLATFORM_SCRIPT" else ""),
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
                "impact": "平台入口需要对执行节点开放，用于下载安装脚本、上报心跳和领取任务。",
                "action": f"在云防火墙/安全组确认 {port}/TCP 的入站规则；来源建议限制为管理员、业务访问方和执行节点公网 IP，处理后点击运行总览的重新检测。",
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
                    "如果执行节点不在同一网络，请改成公网 IP 或域名；如果这是内网专用部署，请确认平台服务器入口端口仅对内网/VPN 开放。",
                    {"host": host},
                    action="操作员确认该控制端地址的网络边界：公网节点请配置公网 IP/域名，内网节点请确认 VPN/内网路由和入口端口策略。",
                    verify_command=health_command,
                    impact="如果执行节点不在同一内网/VPN，会无法下载脚本和上报心跳。",
                    route="/settings?focus=controlPlaneUrl",
                    action_label="确认入口网络策略",
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
                "请确认平台服务器入口端口、安全组、防火墙和 Web/API 容器端口映射；控制端自测公网地址失败可能是 NAT 回环限制，不等于外部不可访问。",
                health,
                action=f"操作员在云控制台或服务器防火墙确认平台入口 {port}/TCP 已按最小来源放行，并确认 docker compose 端口映射和 Web 容器健康。",
                verify_command=health_command,
                impact="如果平台入口端口未正确开放，执行节点后续心跳、领取任务都会失败。",
                action_label="确认平台入口端口",
                category="平台访问入口",
                can_ignore=True,
            )
            installer = self._http_probe(f"{base}/api/v1/agent-installers/linux.sh")
            add_check(
                "agent_installer",
                "安装脚本地址",
                "PASS" if installer["ok"] else "WARN",
                "安装脚本可下载。" if installer["ok"] else f"控制端本机未能确认安装脚本可下载：{installer['message']}。请确认平台入口端口、反向代理和安全组策略。",
                False,
                "请确认平台入口端口和反向代理允许访问 /api/v1/agent-installers/linux.sh；控制端本机自测失败可能是公网回环限制。",
                installer,
                action="操作员确认平台入口端口、安全组、防火墙和 Web/API 反向代理已经放行安装脚本下载路径。",
                verify_command=installer_command,
                impact="安装脚本不可下载时，执行节点无法完成自动接入。",
                action_label="确认安装脚本入口",
                category="平台访问入口",
                can_ignore=True,
            )

        image = str(settings.crawler_agent_image or "").strip()
        if not image:
            add_check(
                "agent_image",
                "执行组件镜像地址",
                "FAIL",
                "未配置执行组件镜像地址，执行节点无法拉取执行组件容器。",
                True,
                "配置 CRAWLER_AGENT_IMAGE 后重启 API/Scheduler/Maintenance，再回到运行总览点击重新检测。",
                action="CI/CD 会在部署阶段自动准备执行组件镜像；页面一键处理需要显式启用白名单动作。当前也可使用兜底命令在平台服务器执行。",
                impact="远程执行节点无法拉取执行组件容器，新增节点无法启动；已在线节点不受影响。",
                route="/dashboard?focus=platformPreflight",
                action_label="准备执行组件镜像",
                category="执行组件镜像分发",
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command,
                action_endpoint="/platform-actions/agent-image-preparations",
                action_button_label="自动准备执行组件镜像",
            )
        elif not self._image_has_registry_prefix(image):
            add_check(
                "agent_image",
                "执行组件镜像地址",
                "FAIL",
                f"执行组件镜像未配置私有仓库前缀：{image}。远程节点会默认从 Docker Hub 拉取，通常无法拉到你的私有镜像。",
                True,
                "将 CRAWLER_AGENT_IMAGE 改成执行节点可访问的完整镜像地址，例如 42.193.226.138:5000/crawler_platform_agent:版本。",
                {"image": image},
                action="CI/CD 会在部署阶段自动准备执行组件镜像；页面一键处理需要显式启用白名单动作。当前也可使用兜底命令在平台服务器执行。",
                impact="远程节点会默认去 Docker Hub 拉你的私有镜像，通常会拉取失败；已在线节点不受影响。",
                route="/dashboard?focus=platformPreflight",
                action_label="自动准备镜像分发",
                category="执行组件镜像分发",
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command,
                action_endpoint="/platform-actions/agent-image-preparations",
                action_button_label="自动准备执行组件镜像",
            )
        else:
            registry = image.split('/', 1)[0]
            registry_host = registry.rsplit(':', 1)[0] if ':' in registry else registry
            registry_port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
            scheme_hint = "http" if registry_port in {5000, 80} or registry_host in {"localhost", "127.0.0.1"} else "https"
            registry_command = f"curl -i {scheme_hint}://{registry}/v2/"
            pull_command = f"docker pull {image}"
            required_ports.append({
                "name": "平台镜像仓库公网访问",
                "host": registry_host,
                "port": registry_port,
                "protocol": "TCP",
                "reason": "执行节点需要从平台镜像仓库拉取执行组件镜像。",
                "impact": "平台镜像仓库需要对执行节点来源 IP 开放，用于拉取执行组件镜像。",
                "action": f"在平台服务器或云安全组确认 {registry_port}/TCP 仅对执行节点来源 IP 放行；HTTP registry 的执行节点 Docker 配置由接入安装流程处理。",
                "actionLabel": "放行镜像仓库端口",
                "verifyCommand": registry_command,
                "automationType": "CLOUD_CONSOLE",
                "handler": "云控制台",
            })
            registry_probe = self._registry_probe(registry)
            add_check(
                "agent_registry",
                "平台镜像仓库公网访问",
                "PASS" if registry_probe["ok"] else "WARN",
                f"平台镜像仓库公网访问可访问：{registry}" if registry_probe["ok"] else f"控制端本机未能确认平台镜像仓库公网访问可访问：{registry_probe['message']}。请确认平台服务器 registry 容器、5000/TCP 监听、云安全组和本机防火墙策略。",
                False,
                "确认平台服务器 registry 容器、本机 5000/TCP 监听、云安全组和防火墙规则；HTTP registry 的节点侧 Docker 配置在执行节点接入流程中处理。",
                {**registry_probe, "image": image, "registry": registry},
                action=f"操作员在云控制台确认平台服务器 {registry_port}/TCP 仅对执行节点来源 IP 放行；不要对全部公网开放。",
                verify_command=registry_command,
                impact="镜像仓库不可达时，远程执行节点无法启动平台执行组件；已在线节点不受影响。",
                action_label="确认仓库端口策略",
                category="执行组件镜像分发",
                can_ignore=True,
                automation_type="CLOUD_CONSOLE",
                handler="云控制台",
                auto_action_command="",
            )
            configured_digest = str(settings.crawler_agent_image_digest or "").strip()
            if configured_digest:
                tag_probe = {"ok": True, "source": "configured_digest", "image": image, "digest": configured_digest}
                tag_status = "PASS"
                tag_message = f"部署阶段已记录执行组件镜像版本：{image}。"
            else:
                tag_probe = self._registry_tag_probe(image)
                tag_status = "PASS" if tag_probe["ok"] else "WARN"
                tag_message = f"执行组件镜像版本可查询：{image}" if tag_probe["ok"] else f"控制端本机未能确认执行组件镜像版本已推送：{tag_probe['message']}。请在执行节点或平台服务器验证 docker pull。"
            add_check(
                "agent_image_tag",
                "执行组件镜像版本",
                tag_status,
                tag_message,
                False,
                "部署阶段已记录镜像校验值时，平台视为镜像版本已准备；否则重新触发 CI/CD 或在平台服务器执行兜底命令确认镜像版本。",
                tag_probe,
                action="CI/CD 会在部署阶段准备执行组件镜像；如版本未确认，请重新触发 CI/CD 或在平台服务器执行兜底命令准备镜像。",
                verify_command="",
                impact="镜像仓库存在但版本未推送时，新增执行节点会在拉取执行组件镜像阶段失败。",
                action_label="重新准备执行组件镜像",
                category="执行组件镜像分发",
                can_ignore=True,
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command,
                action_endpoint="/platform-actions/agent-image-preparations" if tag_status == "FAIL" else "",
                action_button_label="自动准备执行组件镜像" if tag_status == "FAIL" else "",
            )
            if configured_digest:
                digest_probe = {"ok": True, "source": "configured_digest", "digest": configured_digest}
                digest_status = "PASS"
                digest_message = f"部署阶段已记录执行组件镜像校验值：{configured_digest}"
            else:
                digest_probe = self._registry_digest_probe(image)
                digest_status = "PASS" if digest_probe["ok"] else "WARN"
                digest_message = f"执行组件镜像校验值已记录：{digest_probe.get('digest')}" if digest_probe["ok"] else f"未能确认执行组件镜像校验值：{digest_probe['message']}。请用平台脚本重新准备镜像或在执行节点 docker pull 后上报校验值。"
            add_check(
                "agent_image_digest",
                "执行组件镜像校验值",
                digest_status,
                digest_message,
                False,
                "部署阶段会读取 registry manifest 校验值；执行节点心跳也会上报实际运行镜像校验值。",
                digest_probe,
                action="CI/CD 会在部署阶段读取 registry manifest 校验值；如校验值未确认，请重新触发 CI/CD 或在平台服务器执行兜底命令准备镜像。",
                verify_command="",
                impact="未记录校验值时仍可接入，但无法证明镜像版本内容和当前发布版本完全一致。",
                action_label="重新准备执行组件镜像",
                category="执行组件镜像分发",
                can_ignore=True,
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command,
                action_endpoint="/platform-actions/agent-image-preparations" if digest_status == "FAIL" else "",
                action_button_label="自动准备执行组件镜像" if digest_status == "FAIL" else "",
            )
            security = self._registry_security_posture(registry, registry_port, scheme_hint)
            add_check(
                "agent_registry_security",
                "内置镜像仓库安全策略",
                security["status"],
                security["message"],
                False,
                security["suggestion"],
                security,
                action=security["action"],
                verify_command=security.get("verifyCommand", ""),
                impact="内置 registry 若未鉴权且对公网全开放，可能被未授权拉取或污染镜像。",
                action_label="收紧镜像仓库访问",
                category="执行组件镜像分发",
                can_ignore=True,
                automation_type="CLOUD_CONSOLE" if not security.get("authEnabled") else "MANUAL",
                handler="云控制台" if not security.get("authEnabled") else "平台配置",
            )

        blocking_count = sum(1 for item in checks if item["blocking"] and item["status"] == "FAIL")
        warning_count = sum(1 for item in checks if item["status"] == "WARN")
        if blocking_count:
            summary = f"平台自检发现 {blocking_count} 个必须处理项，按提示处理后点击重新检测。"
        elif warning_count:
            summary = f"平台侧没有必须处理项，可以生成接入命令；仍有 {warning_count} 个平台服务器外部访问策略需要超管确认。"
        else:
            summary = "平台自检通过，执行节点接入基础条件已具备。"
        if blocking_count:
            next_action = "先处理平台侧必须处理项；CI/CD 会自动准备执行组件镜像，页面一键处理仅在白名单动作启用时可用。"
        elif warning_count:
            next_action = "请确认云服务器安全组、防火墙和内置镜像仓库访问策略；确认后可继续新增或重新接入执行节点。"
        else:
            next_action = "平台侧接入条件已就绪，可以继续新增或重新接入执行节点。"
        security_group_checklist = self._security_group_checklist(base, required_ports, checks)
        return {
            "readyForRemoteAgent": blocking_count == 0,
            "status": "PASS" if blocking_count == 0 and warning_count == 0 else ("WARN" if blocking_count == 0 else "FAIL"),
            "summary": summary,
            "blockingCount": blocking_count,
            "warningCount": warning_count,
            "checks": checks,
            "requiredPorts": required_ports,
            "controlPlaneUrl": base,
            "agentImage": image,
            "agentImageDigest": settings.crawler_agent_image_digest or self._agent_image_digest_from_checks(checks),
            "checkedAt": checked_at,
            "checkSource": source_key,
            "checkSourceLabel": source_label,
            "nextAction": next_action,
            "automationSummary": self._automation_summary(checks),
            "platformActionEnabled": bool(platform_action_capability.get("enabled")),
            "platformActionAvailable": bool(platform_action_capability.get("available")),
            "platformActionCapability": platform_action_capability,
            "securityGroupChecklist": security_group_checklist,
        }

    @staticmethod
    def _security_group_checklist(control_plane_url: str, required_ports: list[dict], checks: list[dict]) -> dict:
        rules: list[dict] = []
        seen: set[tuple[str, int, str]] = set()
        for item in required_ports:
            port = int(item.get("port") or 0)
            if not port:
                continue
            name = str(item.get("name") or "平台端口")
            protocol = str(item.get("protocol") or "TCP")
            key = (name, port, protocol)
            if key in seen:
                continue
            seen.add(key)
            is_registry = port == int(settings.crawler_agent_registry_port or 5000) or "镜像" in name or "registry" in name.lower()
            rules.append({
                "name": name,
                "protocol": protocol,
                "port": port,
                "source": "执行节点公网 IP" if is_registry else "管理员、业务访问方和执行节点公网 IP",
                "suggestion": "仅允许执行节点公网 IP 访问，不建议 0.0.0.0/0" if is_registry else "按实际访问方最小范围放行，不建议长期全网开放",
                "risk": "内置镜像仓库未启用认证或 TLS 时，全网开放会带来未授权拉取或污染镜像风险。" if is_registry else "入口端口过度开放会扩大平台管理面暴露范围。",
            })
        if not any(int(item.get("port") or 0) == 22 for item in rules):
            rules.append({
                "name": "SSH / CI/CD 入口",
                "protocol": "TCP",
                "port": 22,
                "source": "管理员 IP / CI/CD 来源",
                "suggestion": "仅允许可信运维来源访问；不建议对全部公网开放。",
                "risk": "SSH 全网开放会增加暴力破解和误操作风险。",
            })
        return {
            "title": "平台服务器安全组 / 防火墙规则清单",
            "summary": "请在云服务器控制台和本机防火墙确认以下入站规则；平台无法在未授权情况下自动修改云安全组。",
            "controlPlaneUrl": control_plane_url,
            "rules": rules,
            "notes": [
                "平台自检以控制端服务器为视角：确认本机服务、端口监听、镜像仓库和外部访问策略。",
                "执行节点连通性验证已放到执行节点接入流程；新增节点时再在目标节点执行验证脚本。",
            ],
        }

    @staticmethod
    def _agent_image_digest_from_checks(checks: list[dict]) -> str:
        for item in checks:
            if item.get("key") == "agent_image_digest":
                return str((item.get("details") or {}).get("digest") or "")
        return ""

    @staticmethod
    def _execution_channel(automation_type: str, action_available: bool = False) -> str:
        if automation_type == "PLATFORM_SCRIPT":
            return "PAGE_ACTION" if action_available else "CICD_OR_SERVER_SCRIPT"
        if automation_type == "NODE_INSTALLER_AUTHORIZED":
            return "NODE_INSTALLER"
        if automation_type == "CLOUD_CONSOLE":
            return "CLOUD_CONSOLE"
        return "MANUAL"

    @staticmethod
    def _automation_summary(checks: list[dict]) -> dict:
        summary = {
            "ciCdOrServerScript": 0,
            "pageAction": 0,
            "platformScript": 0,
            "nodeInstallerAuthorized": 0,
            "nodeVerify": 0,
            "cloudConsole": 0,
            "manual": 0,
        }
        for item in checks:
            if item.get("status") == "PASS":
                continue
            kind = str(item.get("automationType") or "MANUAL")
            channel = str(item.get("executionChannel") or "")
            if kind == "PLATFORM_SCRIPT":
                if item.get("actionAvailable"):
                    summary["pageAction"] += 1
                else:
                    summary["ciCdOrServerScript"] += 1
                summary["platformScript"] += 1
            elif kind == "NODE_INSTALLER_AUTHORIZED":
                summary["nodeInstallerAuthorized"] += 1
            elif kind == "CLOUD_CONSOLE":
                summary["cloudConsole"] += 1
            else:
                summary["manual"] += 1
        return summary

    @staticmethod
    def _prepare_agent_image_manual_command() -> str:
        root = str(settings.platform_action_root or "/data/projects/crawler_platform").strip() or "/data/projects/crawler_platform"
        return f"cd {shlex.quote(root)} && bash deploy/scripts/prepare-agent-image.sh"

    def _platform_action_capability_payload(self) -> dict:
        enabled = bool(settings.platform_action_enabled)
        manual_command = self._prepare_agent_image_manual_command()
        if not enabled:
            return {
                "enabled": False,
                "available": False,
                "reason": "当前部署未启用页面白名单动作执行能力；CI/CD 仍会在部署阶段自动处理，页面只展示平台服务器兜底命令和安全组确认引导。",
                "manualCommand": manual_command,
                "channel": "CICD_OR_SERVER_SCRIPT",
            }

        root = Path(settings.platform_action_root).resolve()
        script = root / "deploy" / "scripts" / "prepare-agent-image.sh"
        if not root.exists():
            return {"enabled": True, "available": False, "reason": f"平台动作根目录不存在：{root}", "manualCommand": manual_command, "channel": "CICD_OR_SERVER_SCRIPT"}
        if not script.exists() or not os.access(script, os.R_OK):
            return {"enabled": True, "available": False, "reason": f"平台动作脚本不存在或不可读：{script}", "manualCommand": manual_command, "channel": "CICD_OR_SERVER_SCRIPT"}
        if shutil.which("docker") is None:
            return {"enabled": True, "available": False, "reason": "当前后端运行环境找不到 docker 命令，不能通过页面执行镜像准备动作。", "manualCommand": manual_command, "channel": "CICD_OR_SERVER_SCRIPT"}
        if not os.getenv("DOCKER_HOST") and not Path("/var/run/docker.sock").exists():
            return {"enabled": True, "available": False, "reason": "当前后端运行环境未挂载 Docker socket，不能通过页面执行镜像准备动作。", "manualCommand": manual_command, "channel": "CICD_OR_SERVER_SCRIPT"}
        return {
            "enabled": True,
            "available": True,
            "reason": "页面白名单动作执行能力已启用。",
            "manualCommand": manual_command,
            "channel": "PAGE_ACTION",
        }

    def save_preflight_snapshot(self, preflight: dict, user: SysUser | None = None) -> dict:
        previous = self.latest_preflight_snapshot()
        changes = self._snapshot_changes(previous, preflight)
        preflight["changes"] = changes
        source = str(preflight.get("checkSource") or "AUTO").upper()
        if source == "AUTO" and previous and changes == ["状态无变化"]:
            payload = dict(previous)
            payload["saved"] = False
            payload["changes"] = changes
            return payload
        snapshot = PlatformPreflightSnapshot(
            status=str(preflight.get("status") or "UNKNOWN"),
            blocking_count=int(preflight.get("blockingCount") or 0),
            warning_count=int(preflight.get("warningCount") or 0),
            check_source=str(preflight.get("checkSource") or "AUTO"),
            check_source_label=str(preflight.get("checkSourceLabel") or ""),
            control_plane_url=str(preflight.get("controlPlaneUrl") or ""),
            agent_image=str(preflight.get("agentImage") or ""),
            agent_image_digest=str(preflight.get("agentImageDigest") or ""),
            summary=str(preflight.get("summary") or "")[:500],
            change_summary=changes,
            result_json=preflight,
            triggered_by=user.user_id if user else None,
            checked_at=utcnow(),
            created_at=utcnow(),
        )
        self.db.add(snapshot)
        self.db.flush()
        keep_ids = list(self.db.scalars(select(PlatformPreflightSnapshot.snapshot_id).order_by(PlatformPreflightSnapshot.checked_at.desc()).limit(50)).all())
        if keep_ids:
            self.db.execute(delete(PlatformPreflightSnapshot).where(PlatformPreflightSnapshot.snapshot_id.not_in(keep_ids)))
        self.db.commit()
        return self._snapshot_payload(snapshot)

    def latest_preflight_snapshot(self) -> dict | None:
        row = self.db.scalar(select(PlatformPreflightSnapshot).order_by(PlatformPreflightSnapshot.checked_at.desc()).limit(1))
        return self._snapshot_payload(row) if row else None

    def list_preflight_snapshots(self, limit: int = 10) -> list[dict]:
        rows = list(self.db.scalars(select(PlatformPreflightSnapshot).order_by(PlatformPreflightSnapshot.checked_at.desc()).limit(max(1, min(int(limit or 10), 50)))).all())
        return [self._snapshot_payload(row) for row in rows]

    @staticmethod
    def _snapshot_payload(row: PlatformPreflightSnapshot) -> dict:
        return {
            "snapshotId": row.snapshot_id,
            "status": row.status,
            "blockingCount": row.blocking_count,
            "warningCount": row.warning_count,
            "checkSource": row.check_source,
            "checkSourceLabel": row.check_source_label,
            "controlPlaneUrl": row.control_plane_url,
            "agentImage": row.agent_image,
            "agentImageDigest": row.agent_image_digest,
            "summary": row.summary,
            "changes": row.change_summary or [],
            "checkedAt": row.checked_at,
            "createdAt": row.created_at,
            "triggeredBy": row.triggered_by,
        }

    @staticmethod
    def _snapshot_changes(previous: dict | None, current: dict) -> list[str]:
        if not previous:
            return ["首次保存平台自检快照"]
        changes: list[str] = []
        status_label = {"PASS": "通过", "WARN": "需确认", "FAIL": "必须处理"}
        if previous.get("status") != current.get("status"):
            changes.append(f"总体状态：{status_label.get(str(previous.get('status')), previous.get('status'))} -> {status_label.get(str(current.get('status')), current.get('status'))}")
        if int(previous.get("blockingCount") or 0) != int(current.get("blockingCount") or 0):
            changes.append(f"必须处理项：{previous.get('blockingCount', 0)} -> {current.get('blockingCount', 0)}")
        if int(previous.get("warningCount") or 0) != int(current.get("warningCount") or 0):
            changes.append(f"需确认项：{previous.get('warningCount', 0)} -> {current.get('warningCount', 0)}")
        if str(previous.get("agentImage") or "") != str(current.get("agentImage") or ""):
            changes.append("执行组件镜像地址已变化")
        if str(previous.get("agentImageDigest") or "") != str(current.get("agentImageDigest") or ""):
            changes.append("执行组件镜像校验值已变化")
        return changes[:8] or ["状态无变化"]

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

    def _registry_digest_probe(self, image: str) -> dict:
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
        accept = "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
        for scheme in schemes:
            url = f"{scheme}://{registry}/v2/{repo}/manifests/{tag}"
            try:
                req = UrlRequest(url, headers={"User-Agent": "crawler-platform-preflight/1.0", "Accept": accept})
                with urlopen(req, timeout=1.0) as resp:
                    digest = str(resp.headers.get("Docker-Content-Digest") or "")
                    status_code = int(getattr(resp, "status", 0) or 0)
                    result = {"ok": bool(digest.startswith("sha256:")), "statusCode": status_code, "url": url, "message": f"HTTP {status_code}", "digest": digest, "image": image, "registry": registry, "repository": repo, "tag": tag}
                    attempts.append(result)
                    if result["ok"]:
                        return {**result, "attempts": attempts}
            except HTTPError as exc:
                attempts.append({"ok": False, "statusCode": exc.code, "url": url, "message": f"HTTP {exc.code}", "digest": ""})
            except URLError as exc:
                attempts.append({"ok": False, "statusCode": 0, "url": url, "message": str(getattr(exc, "reason", exc)), "digest": ""})
            except Exception as exc:  # pragma: no cover
                attempts.append({"ok": False, "statusCode": 0, "url": url, "message": str(exc), "digest": ""})
        return {"ok": False, "message": "; ".join(item.get("message", "") for item in attempts) or "无法读取镜像 digest", "image": image, "registry": registry, "attempts": attempts, "digest": ""}

    @staticmethod
    def _registry_security_posture(registry: str, registry_port: int, scheme_hint: str) -> dict:
        auth_enabled = bool(settings.crawler_agent_registry_auth_enabled)
        tls_enabled = bool(settings.crawler_agent_registry_tls_enabled) or scheme_hint == "https"
        is_builtin_http = registry_port == int(settings.crawler_agent_registry_port or 5000) and not tls_enabled
        if auth_enabled and tls_enabled:
            return {"status": "PASS", "message": "镜像仓库已声明启用认证和 HTTPS。", "suggestion": "保持镜像仓库凭据和证书有效，并限制执行节点访问来源。", "action": "定期轮换镜像仓库凭据和证书。", "authEnabled": True, "tlsEnabled": True}
        if is_builtin_http and not auth_enabled:
            return {"status": "WARN", "message": "内置 registry 使用 HTTP 且未声明启用认证，请不要对全部公网开放 5000/TCP。", "suggestion": "在云防火墙/安全组中仅允许执行节点公网 IP 访问 5000/TCP；成熟环境建议切换到 HTTPS/带认证的镜像仓库。", "action": "操作员到云控制台收紧 5000/TCP 来源；需要更高安全级别时配置 CRAWLER_AGENT_REGISTRY_AUTH_ENABLED=1 或使用云厂商镜像仓库。", "verifyCommand": f"curl -i http://{registry}/v2/", "authEnabled": False, "tlsEnabled": False}
        return {"status": "WARN" if not auth_enabled else "PASS", "message": "镜像仓库认证状态未完全确认。" if not auth_enabled else "镜像仓库已声明启用认证。", "suggestion": "确认镜像仓库访问来源、认证和 TLS 策略符合生产要求。", "action": "操作员检查镜像仓库权限策略；如果是公网 registry，建议启用认证和 HTTPS。", "authEnabled": auth_enabled, "tlsEnabled": tls_enabled}

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
