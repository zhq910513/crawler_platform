#!/usr/bin/env python3
"""Guard execution-node onboarding regressions."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
errors: list[str] = []

service = (ROOT / "backend/app/services/server_service.py").read_text(encoding="utf-8")
schemas = (ROOT / "backend/app/schemas.py").read_text(encoding="utf-8")
api = (ROOT / "backend/app/api/agent_bootstrap.py").read_text(encoding="utf-8")
installer = ROOT / "backend/app/templates/install-agent.sh"
frontend = (ROOT / "frontend/src/views/ServersPage.vue").read_text(encoding="utf-8")
settings_page = (ROOT / "frontend/src/views/SettingsPage.vue").read_text(encoding="utf-8")
dashboard_page = (ROOT / "frontend/src/views/DashboardPage.vue").read_text(encoding="utf-8")
system_config_service = (ROOT / "backend/app/services/system_config_service.py").read_text(encoding="utf-8")
companies = (ROOT / "frontend/src/views/CompaniesPage.vue").read_text(encoding="utf-8")
platform_action_service = (ROOT / "backend/app/services/platform_action_service.py").read_text(encoding="utf-8")

if not installer.exists():
    errors.append("backend/app/templates/install-agent.sh 不存在，API 镜像内安装脚本接口会失败")
else:
    text = installer.read_text(encoding="utf-8")
    for token in ["--control-plane-url", "--join-token", "控制端连通", "Docker"]:
        if token not in text:
            errors.append(f"安装脚本缺少关键内容：{token}")

legacy_loopback = "127.0.0.1" + ":" + "8000"
if legacy_loopback in service:
    errors.append("接入命令仍包含内部调试地址 " + legacy_loopback)
if "install_target" not in schemas or "control_plane_url" not in schemas:
    errors.append("接入令牌创建参数缺少 install_target/control_plane_url")
if "detected_base_url" not in (ROOT / "backend/app/api/servers.py").read_text(encoding="utf-8"):
    errors.append("后端未根据请求识别控制端公网回调地址")
if "templates" not in api or "deploy" in re.sub(r"#.*", "", api):
    errors.append("安装脚本接口不应依赖 API 镜像外的 deploy 目录")
if "currentOrigin" not in frontend or "connectivityCommand" not in frontend:
    errors.append("执行节点接入前端缺少系统地址读取或连通性验证命令")

if "controlPlanePreflight" not in system_config_service or "requiredPorts" not in system_config_service:
    errors.append("控制端缺少对外接入预检和必要端口清单，执行节点接入前无法提前暴露安全组/镜像仓库问题")
if "inspect_control_plane_preflight" not in service or "readyForRemoteAgent" not in service or "code=40075" not in service:
    errors.append("后端生成远程接入命令前未强制执行控制端接入预检，直接调用 API 仍可能绕过前端阻断")
if "执行组件镜像仓库" not in system_config_service or "/api/v1/agent-installers/linux.sh" not in system_config_service:
    errors.append("控制端预检未覆盖 执行组件镜像仓库或安装脚本地址")
if "controlPreflight" not in frontend or "接入前检查" not in frontend or "查看运行总览平台自检" not in frontend:
    errors.append("执行节点接入前端未展示控制端接入预检")
if "完整平台自检已移到运行总览" not in settings_page:
    errors.append("系统设置页应只保留控制端地址配置，并提示到运行总览查看完整平台自检")

if "platformPreflight" not in dashboard_page or "平台自检" not in dashboard_page or "重新检测" not in dashboard_page or "平台自检详情" not in dashboard_page or "本次检测变化" not in dashboard_page:
    errors.append("运行总览未作为平台自检主入口展示摘要、详情抽屉和手动重新检测变化")
if "prepareAgentImageAction" not in dashboard_page or "自动准备执行组件镜像" not in dashboard_page or "受控白名单动作" not in dashboard_page:
    errors.append("运行总览平台自检缺少一键准备执行组件镜像的受控动作入口")
if "actionAvailable" not in dashboard_page or "fallbackScriptCandidate" not in dashboard_page or "nodeVerificationCommands" not in dashboard_page:
    errors.append("运行总览必须按真实动作能力区分页面一键处理、平台服务器兜底和执行节点验证")

if "status-chip-grid" not in dashboard_page or "chip-label" not in dashboard_page:
    errors.append("运行总览平台自检状态区必须使用分组胶囊，避免状态、数量和时间挤压在一起")
if "preflightIcon" not in dashboard_page or "?" in re.search(r"preflightIcon[^\n]*", dashboard_page).group(0):
    errors.append("运行总览需确认状态不能继续使用问号图标，应使用信息提示语义")
if "nodeVerificationScript" not in dashboard_page or "执行节点验证脚本" not in dashboard_page or "set -Eeuo pipefail" not in dashboard_page:
    errors.append("运行总览需确认状态必须直接展示可复制的执行节点验证脚本")
if "slice(0, 3)" in dashboard_page and "history-changes" not in dashboard_page:
    errors.append("运行总览当前重点事项不能固定只展示 3 项导致数量不一致")
if "slice(0, 6)" not in dashboard_page or "hiddenProblemCount" not in dashboard_page:
    errors.append("运行总览当前重点事项必须展示更多确认项，并提示剩余项")
if "normalizePreflightText" not in dashboard_page or "必须处理项" not in dashboard_page:
    errors.append("运行总览历史快照必须对旧文案做展示归一")
if "configured_digest" not in system_config_service or "部署阶段已记录执行组件镜像校验值" not in system_config_service:
    errors.append("控制端预检必须使用部署阶段已记录的执行组件镜像校验值降低镜像版本/校验值误报")
if "平台可一键处理" in dashboard_page or "平台脚本可处理" in dashboard_page:
    errors.append("运行总览不能把脚本兜底能力误展示成页面一键处理能力")
if "impact" not in system_config_service or "verifyCommand" not in system_config_service or "checkSourceLabel" not in system_config_service:
    errors.append("控制端预检缺少影响范围、验证命令或检测来源")
if "automationType" not in system_config_service or "autoActionCommand" not in system_config_service or "prepare-agent-image.sh" not in system_config_service or "actionEndpoint" not in system_config_service:
    errors.append("控制端预检未区分可自动处理项，或未给出 执行组件镜像自动准备动作")
if "platformActionCapability" not in system_config_service or "executionChannel" not in system_config_service or "nodeVerificationCommands" not in system_config_service:
    errors.append("控制端预检必须返回平台动作能力、执行通道和节点验证命令，避免页面动作口径误导")
if "--auto-configure-docker-registry" not in text or "insecure-registries" not in text:
    errors.append("Agent 安装脚本缺少授权自动配置 Docker HTTP 私有仓库能力")
if "grep -F '"'"'"$reg"'"'"'" in text or 'grep -F "\\"$reg\\""' not in text:
    errors.append("Agent 安装脚本 Docker insecure-registries 检测必须检查真实 registry 值，不能误查字面量 $reg")
if "--replace-existing-agent" not in text or "CURRENT_STAGE" not in text or "启动 Agent 容器" not in text:
    errors.append("Agent 安装脚本缺少失败阶段标识或已有 Agent 容器替换授权保护")
if "--auto-configure-docker-registry" not in service or "replace_existing_agent" not in service:
    errors.append("后端生成的执行节点接入命令缺少 Docker registry 授权配置或重新接入替换控制")
if 'flags += " --replace-existing-agent"' not in service:
    errors.append("--replace-existing-agent 只能在重新接入场景显式追加，不能作为新增节点默认行为")
prepare_script = (ROOT / "deploy/scripts/prepare-agent-image.sh").read_text(encoding="utf-8") if (ROOT / "deploy/scripts/prepare-agent-image.sh").exists() else ""
if ".env.tmp_prepare_agent_image" not in prepare_script or "本机 registry 中未发现 crawler_platform_agent" not in prepare_script:
    errors.append("执行组件镜像准备脚本缺少安全 .env 写入或精确 tag 验证")
if not (ROOT / "deploy/scripts/prepare-agent-image.sh").exists():
    errors.append("缺少平台侧 执行组件镜像自动准备脚本 deploy/scripts/prepare-agent-image.sh")

workflow_text = (ROOT / ".github/workflows/deploy-test-server.yml").read_text(encoding="utf-8") if (ROOT / ".github/workflows/deploy-test-server.yml").exists() else ""
if "CP_DEPLOY_PUBLIC_HOST" not in workflow_text or "STRICT_AGENT_IMAGE_PREPARE" not in workflow_text:
    errors.append("CI/CD 部署入口必须自动传入公网主机并开启执行组件镜像准备强门禁，避免部署成功后运行总览仍残留镜像地址必须处理项")
if "CP_DEPLOY_PUBLIC_HOST" not in prepare_script or "CRAWLER_AGENT_REGISTRY_PUBLIC_HOST" not in prepare_script:
    errors.append("执行组件镜像准备脚本必须支持 CI/CD 公网主机兜底和 .env 显式 registry 主机配置")

for deploy_name in ["deploy.sh", "release-upgrade.sh", "deploy-single-server.sh"]:
    deploy_text = (ROOT / "deploy/scripts" / deploy_name).read_text(encoding="utf-8")
    if "STRICT_AGENT_IMAGE_PREPARE" not in deploy_text:
        errors.append(f"{deploy_name} 缺少 STRICT_AGENT_IMAGE_PREPARE 强门禁开关")
if 'label="控制端公网回调地址"' in frontend:
    errors.append("执行节点接入前端不应在新增执行节点表单展示控制端公网回调地址输入项")
legacy_token_text = "生成" + "接入" + "凭证"
if legacy_token_text in companies:
    errors.append("公司页面仍使用含糊的“" + legacy_token_text + "”文案")
if "项目发布凭证" in companies:
    errors.append("项目发布凭证不应继续放在公司管理页面")
if "配置助手" not in companies:
    errors.append("公司页面缺少配置助手入口")

if "PLATFORM_ACTION_PREPARE_AGENT_IMAGE" not in platform_action_service or "_ACTION_LOCK" not in platform_action_service or "subprocess.run" not in platform_action_service:
    errors.append("平台自动化动作必须是白名单动作，具备执行锁、阶段结果和操作审计")
if errors:
    print("执行节点接入合约检查失败：", file=sys.stderr)
    for item in errors:
        print("- " + item, file=sys.stderr)
    sys.exit(1)
print("执行节点接入合约检查通过：安装脚本、控制端地址、配置助手和前端向导符合要求。")
