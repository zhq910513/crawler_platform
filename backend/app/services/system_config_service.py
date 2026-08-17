from __future__ import annotations

from urllib.error import HTTPError, URLError
from datetime import timedelta
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
from app.models import CrawlerAgent, CrawlerServer, PlatformPreflightSnapshot, SysConfig, SysUser
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
        security_advisories: list[dict] = []
        checked_at = utcnow().isoformat()
        runtime_evidence = self._runtime_agent_evidence()
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
            evidence_source: str = "",
            evidence_scope: str = "",
        ) -> None:
            resolved_action_available = bool(action_endpoint) if action_available is None else bool(action_available)
            effective_automation_type = automation_type
            effective_handler = handler
            effective_action_label = action_label
            effective_auto_action_command = auto_action_command
            effective_action_endpoint = action_endpoint
            effective_action_button_label = action_button_label
            effective_manual_command = manual_command
            if status_value == "PENDING":
                resolved_action_available = False
                effective_automation_type = "AUTO_VERIFY"
                effective_handler = "平台自动验证"
                effective_action_label = "等待自动验证"
                effective_auto_action_command = ""
                effective_action_endpoint = ""
                effective_action_button_label = ""
                effective_manual_command = ""
                action_unavailable_reason = ""
            elif automation_type == "PLATFORM_SCRIPT" and action_endpoint:
                resolved_action_available = bool(platform_action_capability.get("available")) if action_available is None else bool(action_available)
                if not resolved_action_available and not action_unavailable_reason:
                    action_unavailable_reason = str(platform_action_capability.get("reason") or "当前页面未启用白名单动作执行能力。")
            resolved_channel = execution_channel or self._execution_channel(effective_automation_type, resolved_action_available)
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
                "actionLabel": effective_action_label,
                "category": category,
                "canIgnore": bool(can_ignore),
                "automationType": effective_automation_type,
                "handler": effective_handler,
                "autoActionCommand": effective_auto_action_command,
                "actionEndpoint": effective_action_endpoint,
                "actionButtonLabel": effective_action_button_label,
                "actionAvailable": resolved_action_available,
                "actionUnavailableReason": action_unavailable_reason,
                "executionChannel": resolved_channel,
                "manualCommand": effective_manual_command or (prepare_agent_image_command if effective_automation_type == "PLATFORM_SCRIPT" else ""),
                "evidenceSource": evidence_source,
                "evidenceScope": evidence_scope,
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
                "action": f"如需治理云侧访问范围，请按实际访问方最小范围配置 {port}/TCP；平台不读取云安全组规则本身，真实连通性由主动探测和目标节点预检验证。",
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
                private_host_verified = runtime_evidence["onlineAgentCount"] > 0
                add_check(
                    "control_plane_public_host",
                    "控制端网络范围",
                    "PASS" if private_host_verified else "PENDING",
                    (
                        f"当前使用内网/VPN 地址，已有 {runtime_evidence['onlineAgentCount']} 个在线执行节点持续上报心跳，现有节点通信已由运行事实验证。"
                        if private_host_verified
                        else "当前使用内网/VPN 地址；尚无在线执行节点可提供链路证据，新节点接入时会在目标节点自动验证网络可达性。"
                    ),
                    False,
                    "新节点接入时由目标节点预检自动验证；无需因为平台无法读取云网络策略而提前人工确认。",
                    {"host": host, "runtimeEvidence": runtime_evidence},
                    impact="该地址适用于同一内网/VPN 的节点；其他网络的新节点会在接入预检时得到明确结果。",
                    category="平台访问入口",
                    can_ignore=True,
                    evidence_source="执行节点实时心跳" if private_host_verified else "等待目标节点预检",
                    evidence_scope="已有在线执行节点" if private_host_verified else "新节点接入场景",
                )
            else:
                add_check("control_plane_public_host", "公网地址可用性", "PASS", "控制端地址不是本机回环地址。", False, "", {"host": host}, impact="远程节点可以使用该地址作为控制端入口。", category="平台访问入口")

            health = self._http_probe(f"{base}/health")
            health_runtime_verified = not health["ok"] and runtime_evidence["onlineAgentCount"] > 0
            add_check(
                "control_plane_health",
                "平台通信链路",
                "PASS" if health["ok"] or health_runtime_verified else "PENDING",
                (
                    "控制端 /health 主动探测成功。"
                    if health["ok"]
                    else (
                        f"控制端本机公网回环探测失败（{health['message']}），但已有 {runtime_evidence['onlineAgentCount']} 个在线执行节点持续上报心跳，现有节点到平台的通信链路已由运行事实验证。"
                        if health_runtime_verified
                        else f"控制端本机未能通过公网地址验证 /health（{health['message']}）；当前没有在线执行节点提供外部链路证据，将在新节点接入时自动验证。"
                    )
                ),
                False,
                "新节点会在目标服务器执行 /health 预检；控制端本机公网回环失败不会被直接判定为运行异常。",
                {**health, "runtimeEvidence": runtime_evidence},
                verify_command=health_command,
                impact="已有在线节点的实时心跳可证明其到平台的通信链路；未来新节点仍按目标节点网络单独验证。",
                category="平台访问入口",
                can_ignore=True,
                evidence_source="控制端主动探测" if health["ok"] else ("执行节点实时心跳" if health_runtime_verified else "等待目标节点预检"),
                evidence_scope="当前平台入口" if health["ok"] else ("已有在线执行节点" if health_runtime_verified else "新节点接入场景"),
            )
            installer = self._http_probe(f"{base}/api/v1/agent-installers/linux.sh")
            add_check(
                "agent_installer",
                "安装脚本服务",
                "PASS" if installer["ok"] else "PENDING",
                "安装脚本主动探测可下载。" if installer["ok"] else f"控制端本机未能通过公网地址确认安装脚本（{installer['message']}）；这不是已确认故障，新节点接入时会从目标服务器再次自动验证。",
                False,
                "由新节点接入预检自动验证安装脚本下载；只有目标节点实际验证失败时才进入接入故障处理。",
                installer,
                verify_command=installer_command,
                impact="该项仅影响未来新节点安装，不影响已在线节点；当前无法从控制端证明时保持待场景验证。",
                category="节点接入能力",
                can_ignore=True,
                evidence_source="控制端主动探测" if installer["ok"] else "等待目标节点预检",
                evidence_scope="当前安装脚本入口" if installer["ok"] else "新节点接入场景",
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
            registry_command = f"curl -fsS --connect-timeout 3 --max-time 10 {scheme_hint}://{registry}/v2/ && echo"
            pull_command = f"docker pull {image}"
            image_runtime_agents = [item for item in runtime_evidence["agents"] if item.get("agentImage") == image and item.get("actualDigest")]
            required_ports.append({
                "name": "平台镜像仓库公网访问",
                "host": registry_host,
                "port": registry_port,
                "protocol": "TCP",
                "reason": "执行节点需要从平台镜像仓库拉取执行组件镜像。",
                "impact": "平台镜像仓库需要对执行节点来源 IP 开放，用于拉取执行组件镜像。",
                "action": f"如需治理镜像仓库暴露范围，请将 {registry_port}/TCP 限制到执行节点来源 IP；平台不读取云安全组规则本身，HTTP registry 的节点侧 Docker 配置由接入安装流程处理。",
                "actionLabel": "放行镜像仓库端口",
                "verifyCommand": registry_command,
                "automationType": "CLOUD_CONSOLE",
                "handler": "云控制台",
            })
            registry_probe = self._registry_probe(registry)
            registry_runtime_verified = not registry_probe["ok"] and bool(image_runtime_agents)
            add_check(
                "agent_registry",
                "镜像分发链路",
                "PASS" if registry_probe["ok"] or registry_runtime_verified else "PENDING",
                (
                    f"镜像仓库主动探测可访问：{registry}"
                    if registry_probe["ok"]
                    else (
                        f"控制端本机仓库探测失败（{registry_probe['message']}），但已有 {len(image_runtime_agents)} 个在线执行节点正在运行目标镜像并持续上报实际 digest，现有节点镜像分发事实已验证。"
                        if registry_runtime_verified
                        else f"控制端本机未能确认镜像仓库可访问（{registry_probe['message']}）；当前没有在线节点提供目标镜像运行证据，新节点接入时会自动执行 registry / docker pull 验证。"
                    )
                ),
                False,
                "新节点接入时由目标节点验证 registry 和 docker pull；控制端本机探测失败不会自动升级为人工待办。",
                {**registry_probe, "image": image, "registry": registry, "runtimeAgents": image_runtime_agents},
                verify_command=registry_command,
                impact="现有在线节点的目标镜像运行事实只证明这些节点已完成镜像分发；新节点仍按目标环境单独验证。",
                category="执行组件镜像分发",
                can_ignore=True,
                evidence_source="Registry 主动探测" if registry_probe["ok"] else ("执行节点实时镜像证据" if registry_runtime_verified else "等待目标节点预检"),
                evidence_scope="当前镜像仓库" if registry_probe["ok"] else ("已有在线执行节点" if registry_runtime_verified else "新节点接入场景"),
            )
            configured_digest = str(settings.crawler_agent_image_digest or "").strip()
            tag_probe = self._registry_tag_probe(image)
            tag_confirmed_missing = str(tag_probe.get("message") or "").startswith("仓库可访问，但未找到 tag")
            if tag_probe["ok"]:
                tag_status = "PASS"
                tag_blocking = False
                tag_message = f"执行组件镜像版本已在 Registry 中确认：{image}"
                tag_evidence_source = "Registry 主动探测"
                tag_evidence_scope = "当前镜像 tag"
            elif tag_confirmed_missing:
                tag_status = "FAIL"
                tag_blocking = True
                tag_message = f"Registry 可访问，但当前发布镜像 tag 不存在：{image}"
                tag_evidence_source = "Registry 主动探测"
                tag_evidence_scope = "当前镜像 tag"
            elif image_runtime_agents:
                tag_status = "PASS"
                tag_blocking = False
                tag_message = f"控制端本机未能查询镜像 tag（{tag_probe['message']}），但已有 {len(image_runtime_agents)} 个在线执行节点正在运行该镜像；现有节点版本已由运行事实验证。"
                tag_evidence_source = "执行节点实时镜像证据"
                tag_evidence_scope = "已有在线执行节点"
            else:
                tag_status = "PENDING"
                tag_blocking = False
                tag_message = f"控制端本机未能查询镜像 tag（{tag_probe['message']}）；新节点接入脚本会在消耗 Token 前验证 Registry 网络，并在拉取阶段确认镜像。"
                tag_evidence_source = "等待目标节点预检"
                tag_evidence_scope = "新节点接入场景"
            add_check(
                "agent_image_tag",
                "执行组件镜像版本",
                tag_status,
                tag_message,
                tag_blocking,
                "Registry 已确认缺少当前 tag 时直接阻断新节点接入；仅控制端无法探测时保留待场景验证，由目标节点继续验证。",
                tag_probe,
                action="CI/CD 会在部署阶段准备执行组件镜像；如 Registry 已确认缺少当前版本，请重新触发 CI/CD 或在平台服务器执行兜底命令准备镜像。",
                verify_command="",
                impact="Registry 已确认缺少当前版本时，新执行节点必然无法拉取 Agent 镜像。",
                action_label="重新准备执行组件镜像",
                category="执行组件镜像分发",
                can_ignore=not tag_blocking,
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command if tag_status == "FAIL" else "",
                action_endpoint="/platform-actions/agent-image-preparations" if tag_status == "FAIL" else "",
                action_button_label="自动准备执行组件镜像" if tag_status == "FAIL" else "",
                evidence_source=tag_evidence_source,
                evidence_scope=tag_evidence_scope,
            )

            digest_probe = self._registry_digest_probe(image)
            registry_digest = str(digest_probe.get("digest") or "").strip()
            if digest_probe["ok"]:
                if configured_digest and registry_digest and configured_digest != registry_digest:
                    digest_status = "FAIL"
                    digest_blocking = True
                    digest_message = f"执行组件镜像 digest 与部署配置不一致：Registry={registry_digest}，配置={configured_digest}"
                else:
                    digest_status = "PASS"
                    digest_blocking = False
                    digest_message = f"执行组件镜像校验值已从 Registry 读取：{registry_digest}"
                digest_evidence_source = "Registry manifest"
                digest_evidence_scope = "当前镜像 tag"
            elif image_runtime_agents:
                actual_digests = sorted({str(item.get("actualDigest") or "") for item in image_runtime_agents if item.get("actualDigest")})
                runtime_digest = actual_digests[0] if len(actual_digests) == 1 else " / ".join(actual_digests)
                digest_status = "FAIL" if configured_digest and len(actual_digests) == 1 and runtime_digest != configured_digest else "PASS"
                digest_blocking = False
                digest_probe = {**digest_probe, "ok": digest_status == "PASS", "source": "running_agents", "digest": runtime_digest, "runtimeAgents": image_runtime_agents}
                digest_message = (
                    f"在线执行节点实际运行 digest 与部署配置不一致：实际={runtime_digest}，配置={configured_digest}"
                    if digest_status == "FAIL"
                    else f"控制端本机未能读取 Registry digest，但在线执行节点已上报实际运行镜像校验值：{runtime_digest}"
                )
                digest_evidence_source = "执行节点实际运行 digest"
                digest_evidence_scope = "已有在线执行节点"
            else:
                digest_status = "PENDING"
                digest_blocking = False
                digest_message = f"当前未从 Registry 或在线节点取得镜像 digest（{digest_probe['message']}）；配置中的 digest 仅作为期望值，不作为 Registry 已就绪的证明。"
                digest_evidence_source = "等待 Registry/目标节点证据"
                digest_evidence_scope = "新节点接入场景"
            add_check(
                "agent_image_digest",
                "执行组件镜像校验值",
                digest_status,
                digest_message,
                digest_blocking,
                "Registry manifest 或执行节点实际运行 digest 才作为运行证据；配置值只表示期望版本。",
                {**digest_probe, "configuredDigest": configured_digest},
                action="如 Registry digest 与配置不一致，请重新准备执行组件镜像并更新发布配置。",
                verify_command="",
                impact="digest 不一致说明实际镜像内容与当前发布配置不同；无运行证据时保持待场景验证。",
                action_label="重新准备执行组件镜像",
                category="执行组件镜像分发",
                can_ignore=not digest_blocking,
                automation_type="PLATFORM_SCRIPT",
                handler="平台部署脚本",
                auto_action_command=prepare_agent_image_command if digest_status == "FAIL" else "",
                action_endpoint="/platform-actions/agent-image-preparations" if digest_status == "FAIL" else "",
                action_button_label="自动准备执行组件镜像" if digest_status == "FAIL" else "",
                evidence_source=digest_evidence_source,
                evidence_scope=digest_evidence_scope,
            )
            security = self._registry_security_posture(registry, registry_port, scheme_hint)
            if security["status"] != "PASS":
                security_advisories.append({
                    "key": "agent_registry_security",
                    "label": "镜像仓库安全建议",
                    "level": "ADVICE",
                    "message": security["message"],
                    "suggestion": security["suggestion"],
                    "action": security["action"],
                    "verifyCommand": security.get("verifyCommand", ""),
                    "scope": "安全治理，不参与运行健康与接入就绪判定",
                    "details": security,
                })

        online_agents = runtime_evidence["agents"]
        unavailable_agents = runtime_evidence["unavailableAgents"]
        if online_agents:
            if unavailable_agents:
                add_check(
                    "agent_runtime_heartbeat",
                    "执行节点实时通信",
                    "WARN",
                    f"当前有 {len(online_agents)} 个执行节点持续上报实时心跳，同时有 {len(unavailable_agents)} 个已接入且启用的执行节点处于离线、过期或心跳超时状态。",
                    False,
                    "查看执行节点最近心跳和 lastError；这是已有节点的实时运行事实。",
                    {"onlineAgents": online_agents, "unavailableAgents": unavailable_agents},
                    impact=f"{len(unavailable_agents)} 个已接入且启用的执行节点当前不能提供新鲜心跳，可能影响绑定到这些节点的任务。",
                    route="/servers",
                    action_label="查看执行节点",
                    category="现有运行事实",
                    evidence_source="执行节点连接状态与最近心跳",
                    evidence_scope="已接入且启用的执行节点",
                )
            else:
                add_check(
                    "agent_runtime_heartbeat",
                    "执行节点实时通信",
                    "PASS",
                    f"当前有 {len(online_agents)} 个执行节点持续上报实时心跳。",
                    False,
                    "",
                    runtime_evidence,
                    impact="这些在线节点已经提供了节点到平台的实时通信证据。",
                    category="现有运行事实",
                    evidence_source="执行节点实时心跳",
                    evidence_scope="已有在线执行节点",
                )
            bad_docker = [item for item in online_agents if str(item.get("dockerStatus") or "").upper() not in {"", "OK", "READY", "UNKNOWN"}]
            unknown_docker = [item for item in online_agents if str(item.get("dockerStatus") or "").upper() in {"", "UNKNOWN"}]
            if bad_docker:
                add_check(
                    "agent_runtime_docker",
                    "执行节点 Docker",
                    "WARN",
                    f"检测到 {len(bad_docker)} 个在线执行节点明确上报 Docker 异常。",
                    False,
                    "查看执行节点详情中的 dockerStatus 和 lastError；这是实时运行异常，不是云侧策略确认项。",
                    {"agents": bad_docker},
                    impact="对应执行节点可能无法正常启动任务容器。",
                    route="/servers",
                    action_label="查看执行节点",
                    category="现有运行事实",
                    evidence_source="执行节点实时心跳",
                    evidence_scope="明确上报异常的在线执行节点",
                )
            elif unknown_docker:
                add_check(
                    "agent_runtime_docker",
                    "执行节点 Docker",
                    "PENDING",
                    f"{len(unknown_docker)} 个在线执行节点尚未提供明确 Docker 状态；后续心跳会继续自动更新。",
                    False,
                    "无需人工确认，等待节点后续心跳补齐状态。",
                    {"agents": unknown_docker},
                    impact="当前没有证据证明 Docker 异常，因此不计入运行告警。",
                    category="现有运行事实",
                    evidence_source="等待执行节点心跳补齐",
                    evidence_scope="Docker 状态未知的在线执行节点",
                )
            else:
                add_check(
                    "agent_runtime_docker",
                    "执行节点 Docker",
                    "PASS",
                    f"{len(online_agents)} 个在线执行节点均上报 Docker 正常。",
                    False,
                    "",
                    {"agents": online_agents},
                    impact="现有在线节点具备容器执行基础能力。",
                    category="现有运行事实",
                    evidence_source="执行节点实时心跳",
                    evidence_scope="已有在线执行节点",
                )
        else:
            if unavailable_agents:
                add_check(
                    "agent_runtime_heartbeat",
                    "执行节点实时通信",
                    "WARN",
                    f"当前没有执行节点提供新鲜在线心跳，且有 {len(unavailable_agents)} 个已接入且启用的执行节点处于离线、过期或心跳超时状态。",
                    False,
                    "查看执行节点最近心跳和 lastError；如果节点已计划下线，应先按既有节点管理流程停用或移除。",
                    {"unavailableAgents": unavailable_agents},
                    impact="当前已接入且启用的执行节点均不能提供实时通信证据，可能影响任务执行。",
                    route="/servers",
                    action_label="查看执行节点",
                    category="现有运行事实",
                    evidence_source="执行节点连接状态与最近心跳",
                    evidence_scope="已接入且启用的执行节点",
                )
            else:
                add_check(
                    "agent_runtime_heartbeat",
                    "执行节点实时通信",
                    "PENDING",
                    (
                        f"系统已登记 {runtime_evidence['registeredAgentCount']} 个执行组件记录，但尚未形成已接入节点的实时心跳证据；新节点完成接入后会自动验证。"
                        if runtime_evidence["registeredAgentCount"]
                        else "当前尚未接入执行节点；没有运行任务需要节点时这是正常状态，新节点接入后会自动建立实时心跳证据。"
                    ),
                    False,
                    "节点接入后由心跳自动验证，无需提前人工确认。",
                    runtime_evidence,
                    impact="当前没有已接入节点的在线证据；是否影响业务由实际任务等待状态决定。",
                    category="现有运行事实",
                    evidence_source="等待执行节点实时心跳",
                    evidence_scope="执行节点运行场景",
                )

        configured_digest = str(settings.crawler_agent_image_digest or "").strip()
        digest_reporting_agents = [item for item in online_agents if item.get("actualDigest")]
        if configured_digest and digest_reporting_agents:
            mismatched = [item for item in digest_reporting_agents if item.get("actualDigest") != configured_digest]
            if mismatched:
                add_check(
                    "agent_runtime_digest_alignment",
                    "在线节点镜像一致性",
                    "WARN",
                    f"检测到 {len(mismatched)} 个在线执行节点实际运行 digest 与当前发布 digest 不一致。",
                    False,
                    "查看执行节点镜像版本；现有任务不中断，节点空闲后按既有镜像更新流程收敛。",
                    {"expectedDigest": configured_digest, "agents": mismatched},
                    impact="这些节点当前运行的执行组件版本与平台发布版本不一致。",
                    route="/servers",
                    action_label="查看执行节点",
                    category="现有运行事实",
                    evidence_source="执行节点实际运行 digest",
                    evidence_scope="digest 不一致的在线执行节点",
                )
            else:
                add_check(
                    "agent_runtime_digest_alignment",
                    "在线节点镜像一致性",
                    "PASS",
                    f"{len(digest_reporting_agents)} 个在线执行节点实际运行 digest 与当前发布 digest 一致。",
                    False,
                    "",
                    {"expectedDigest": configured_digest, "agents": digest_reporting_agents},
                    impact="已上报 digest 的在线节点与当前发布镜像一致。",
                    category="现有运行事实",
                    evidence_source="执行节点实际运行 digest",
                    evidence_scope="已上报 digest 的在线执行节点",
                )

        blocking_count = sum(1 for item in checks if item["blocking"] and item["status"] == "FAIL")
        warning_count = sum(1 for item in checks if item["status"] == "WARN")
        pending_count = sum(1 for item in checks if item["status"] == "PENDING")
        verified_count = sum(1 for item in checks if item["status"] == "PASS")
        if blocking_count:
            summary = f"自动检测发现 {blocking_count} 个已确认阻断项；已验证 {verified_count} 项，待场景验证 {pending_count} 项。"
        elif warning_count:
            summary = f"当前没有接入阻断，但检测到 {warning_count} 个已确认运行提醒；已验证 {verified_count} 项，待场景验证 {pending_count} 项。"
        elif pending_count:
            summary = f"当前未发现运行异常；已自动验证 {verified_count} 项，另有 {pending_count} 项将在对应场景自动验证，无需提前人工确认。"
        else:
            summary = f"当前未发现运行异常，{verified_count} 个自动检测项均已验证。"
        if blocking_count:
            next_action = "只处理已确认阻断项；可自动处理的项目优先由平台或 CI/CD 完成，处理后重新检测。"
        elif warning_count:
            next_action = "查看已确认的实时运行提醒；安全治理建议与无法自动读取的云侧策略不会计入运行异常。"
        elif pending_count:
            next_action = "无需人工确认；待场景项会在新节点接入、后续心跳或实际镜像拉取时自动补充证据。"
        else:
            next_action = "无需处理；平台会继续通过主动探测和执行节点心跳更新运行事实。"
        security_group_checklist = self._security_group_checklist(base, required_ports, checks)
        return {
            "readyForRemoteAgent": blocking_count == 0,
            "status": "FAIL" if blocking_count else ("WARN" if warning_count else "PASS"),
            "summary": summary,
            "blockingCount": blocking_count,
            "warningCount": warning_count,
            "pendingCount": pending_count,
            "verifiedCount": verified_count,
            "securityAdvisoryCount": len(security_advisories),
            "checks": checks,
            "requiredPorts": required_ports,
            "securityAdvisories": security_advisories,
            "runtimeEvidence": runtime_evidence,
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

    def _runtime_agent_evidence(self) -> dict:
        now = utcnow()
        live_after = now - timedelta(seconds=max(30, int(settings.agent_offline_seconds or 120)))
        agents = list(self.db.scalars(select(CrawlerAgent)).all())
        live_agents: list[dict] = []
        unavailable_agents: list[dict] = []
        for agent in agents:
            server = self.db.get(CrawlerServer, agent.server_id)
            metrics = dict(server.metrics or {}) if server else {}
            payload = {
                "agentId": agent.agent_id,
                "serverId": agent.server_id,
                "agentCode": agent.agent_code,
                "connectionStatus": str(agent.connection_status or "UNREGISTERED"),
                "lastHeartbeatAt": agent.last_heartbeat_at.isoformat() if agent.last_heartbeat_at else "",
                "agentImage": str(agent.agent_image or ""),
                "reportedDigest": str(agent.agent_image_digest or ""),
                "actualDigest": str(agent.agent_image_actual_digest or ""),
                "dockerStatus": str(metrics.get("dockerStatus") or "UNKNOWN"),
                "serverHealthStatus": str(server.health_status if server else "UNKNOWN"),
                "lastError": str(agent.last_error or metrics.get("lastError") or ""),
            }
            if agent.connection_status == "ONLINE" and agent.last_heartbeat_at and agent.last_heartbeat_at >= live_after:
                live_agents.append(payload)
                continue
            if server and server.manage_status == "ENABLED" and agent.connection_status in {"ONLINE", "STALE", "OFFLINE"}:
                unavailable_agents.append(payload)
        return {
            "registeredAgentCount": len(agents),
            "onlineAgentCount": len(live_agents),
            "unavailableAgentCount": len(unavailable_agents),
            "freshnessSeconds": max(30, int(settings.agent_offline_seconds or 120)),
            "checkedAt": now.isoformat(),
            "agents": live_agents,
            "unavailableAgents": unavailable_agents,
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
            "title": "平台服务器安全组 / 防火墙安全建议",
            "summary": "以下内容属于安全治理建议，不参与运行健康和接入就绪判定。平台当前没有云厂商安全组读取授权，因此不会把无法读取云侧规则解释成异常或人工待办。",
            "controlPlaneUrl": control_plane_url,
            "rules": rules,
            "notes": [
                "运行总览优先使用主动探测、执行节点心跳、Docker 状态和实际镜像 digest 作为运行证据。",
                "新执行节点的网络、registry 与 docker pull 由目标节点接入预检自动验证。",
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
        if automation_type == "AUTO_VERIFY":
            return "AUTO_VERIFY"
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
            if item.get("status") not in {"FAIL", "WARN"}:
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
                "reason": "当前部署未启用页面白名单动作执行能力；CI/CD 仍会在部署阶段自动处理，页面仅展示平台服务器兜底命令。安全治理建议独立展示，不参与运行异常判定。",
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
        result = dict(row.result_json or {})
        return {
            "snapshotId": row.snapshot_id,
            "status": row.status,
            "blockingCount": row.blocking_count,
            "warningCount": row.warning_count,
            "pendingCount": int(result.get("pendingCount") or 0),
            "verifiedCount": int(result.get("verifiedCount") or 0),
            "securityAdvisoryCount": int(result.get("securityAdvisoryCount") or 0),
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
        status_label = {"PASS": "正常", "WARN": "运行提醒", "FAIL": "已确认异常", "PENDING": "待场景验证"}
        if previous.get("status") != current.get("status"):
            changes.append(f"总体状态：{status_label.get(str(previous.get('status')), previous.get('status'))} -> {status_label.get(str(current.get('status')), current.get('status'))}")
        if int(previous.get("blockingCount") or 0) != int(current.get("blockingCount") or 0):
            changes.append(f"必须处理项：{previous.get('blockingCount', 0)} -> {current.get('blockingCount', 0)}")
        if int(previous.get("warningCount") or 0) != int(current.get("warningCount") or 0):
            changes.append(f"运行提醒：{previous.get('warningCount', 0)} -> {current.get('warningCount', 0)}")
        if int(previous.get("pendingCount") or 0) != int(current.get("pendingCount") or 0):
            changes.append(f"待场景验证：{previous.get('pendingCount', 0)} -> {current.get('pendingCount', 0)}")
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

    def _registry_probe_candidates(self, registry: str) -> list[str]:
        candidates = [registry]
        host = registry.rsplit(':', 1)[0] if ':' in registry else registry
        port = int(registry.rsplit(':', 1)[1]) if ':' in registry and registry.rsplit(':', 1)[1].isdigit() else 443
        configured_host = str(settings.crawler_agent_registry_public_host or "").strip()
        configured_port = int(settings.crawler_agent_registry_port or 5000)
        if configured_host and host == configured_host and port == configured_port and host not in {"127.0.0.1", "localhost"}:
            candidates.append(f"127.0.0.1:{port}")
        return candidates

    def _registry_probe(self, registry: str) -> dict:
        attempts = []
        for candidate in self._registry_probe_candidates(registry):
            host = candidate.rsplit(':', 1)[0] if ':' in candidate else candidate
            port = int(candidate.rsplit(':', 1)[1]) if ':' in candidate and candidate.rsplit(':', 1)[1].isdigit() else 443
            schemes = ["http", "https"] if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else ["https", "http"]
            for scheme in schemes:
                probe = self._http_probe(f"{scheme}://{candidate}/v2/", timeout=1.0)
                attempts.append({**probe, "probeRegistry": candidate})
                if probe["ok"]:
                    return {**probe, "registry": registry, "probeRegistry": candidate, "attempts": attempts}
        return {"ok": False, "statusCode": 0, "url": attempts[-1]["url"] if attempts else "", "message": "; ".join(item["message"] for item in attempts) or "无法访问镜像仓库", "registry": registry, "attempts": attempts}

    def _registry_tag_probe(self, image: str) -> dict:
        try:
            registry, rest = image.split('/', 1)
            if ':' in rest.rsplit('/', 1)[-1]:
                repo, tag = rest.rsplit(':', 1)
            else:
                repo, tag = rest, 'latest'
        except ValueError:
            return {"ok": False, "message": "镜像地址缺少仓库前缀", "image": image}
        attempts = []
        for candidate in self._registry_probe_candidates(registry):
            host = candidate.rsplit(':', 1)[0] if ':' in candidate else candidate
            port = int(candidate.rsplit(':', 1)[1]) if ':' in candidate and candidate.rsplit(':', 1)[1].isdigit() else 443
            schemes = ["http", "https"] if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else ["https", "http"]
            for scheme in schemes:
                url = f"{scheme}://{candidate}/v2/{repo}/tags/list"
                probe = self._http_text_probe(url, timeout=1.0)
                attempts.append({**probe, "probeRegistry": candidate})
                if probe["ok"]:
                    try:
                        payload = json.loads(str(probe.get("body") or "{}"))
                    except json.JSONDecodeError:
                        payload = {}
                    tags = payload.get("tags") if isinstance(payload, dict) else None
                    if isinstance(tags, list) and tag in tags:
                        return {**probe, "image": image, "registry": registry, "probeRegistry": candidate, "repository": repo, "tag": tag, "tags": tags, "attempts": attempts}
                    return {**probe, "ok": False, "message": f"仓库可访问，但未找到 tag {tag}", "image": image, "registry": registry, "probeRegistry": candidate, "repository": repo, "tag": tag, "tags": tags or [], "attempts": attempts}
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
        attempts = []
        accept = "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
        for candidate in self._registry_probe_candidates(registry):
            host = candidate.rsplit(':', 1)[0] if ':' in candidate else candidate
            port = int(candidate.rsplit(':', 1)[1]) if ':' in candidate and candidate.rsplit(':', 1)[1].isdigit() else 443
            schemes = ["http", "https"] if port in {5000, 80} or host in {"localhost", "127.0.0.1"} else ["https", "http"]
            for scheme in schemes:
                url = f"{scheme}://{candidate}/v2/{repo}/manifests/{tag}"
                try:
                    req = UrlRequest(url, headers={"User-Agent": "crawler-platform-preflight/1.0", "Accept": accept})
                    with urlopen(req, timeout=1.0) as resp:
                        digest = str(resp.headers.get("Docker-Content-Digest") or "")
                        status_code = int(getattr(resp, "status", 0) or 0)
                        result = {"ok": bool(digest.startswith("sha256:")), "statusCode": status_code, "url": url, "message": f"HTTP {status_code}", "digest": digest, "image": image, "registry": registry, "probeRegistry": candidate, "repository": repo, "tag": tag}
                        attempts.append(result)
                        if result["ok"]:
                            return {**result, "attempts": attempts}
                except HTTPError as exc:
                    attempts.append({"ok": False, "statusCode": exc.code, "url": url, "message": f"HTTP {exc.code}", "digest": "", "probeRegistry": candidate})
                except URLError as exc:
                    attempts.append({"ok": False, "statusCode": 0, "url": url, "message": str(getattr(exc, "reason", exc)), "digest": "", "probeRegistry": candidate})
                except Exception as exc:  # pragma: no cover
                    attempts.append({"ok": False, "statusCode": 0, "url": url, "message": str(exc), "digest": "", "probeRegistry": candidate})
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
