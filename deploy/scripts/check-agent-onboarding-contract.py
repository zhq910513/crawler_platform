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
agent_main = (ROOT / "agent/crawler_agent/main.py").read_text(encoding="utf-8")

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
dictionary_text = (ROOT / "frontend/src/utils/dictionaries.ts").read_text(encoding="utf-8")
if "isNaiveUtc" not in dictionary_text or "`${raw}Z`" not in dictionary_text:
    errors.append("前端统一时间格式化必须把后端无时区标记的 UTC ISO 时间按 UTC 解析，避免少 8 小时")

if "controlPlanePreflight" not in system_config_service or "requiredPorts" not in system_config_service:
    errors.append("控制端缺少对外接入预检和必要端口清单，执行节点接入前无法提前暴露安全组/镜像仓库问题")
if "inspect_control_plane_preflight" not in service or "readyForRemoteAgent" not in service or "code=40075" not in service:
    errors.append("后端生成远程接入命令前未强制执行控制端接入预检，直接调用 API 仍可能绕过前端阻断")
if "平台镜像仓库公网访问" not in system_config_service or "/api/v1/agent-installers/linux.sh" not in system_config_service:
    errors.append("控制端预检未覆盖平台镜像仓库公网访问或安装脚本地址")
if "controlPreflight" not in frontend or "接入前检查" not in frontend or "查看平台状态" not in frontend:
    errors.append("执行节点接入前端未展示控制端接入预检")
if "运行总览会自动检测当前可证明的运行条件" not in settings_page:
    errors.append("系统设置页必须说明运行总览按真实证据自动检测，控制端无法证明的网络项等待目标节点验证")

if "执行节点验证脚本" in dashboard_page or "复制执行节点验证" in dashboard_page:
    errors.append("运行总览平台自检不能再引导复制执行节点验证脚本")
if "platformPreflight" not in dashboard_page or "平台状态详情" not in dashboard_page or "重新检测" not in dashboard_page or "检测历史" not in dashboard_page:
    errors.append("运行总览必须保留真实状态详情、手动重新检测和检测历史下钻能力")
if "prepareAgentImageAction" not in dashboard_page or "受控白名单动作" not in dashboard_page or "自动处理" not in dashboard_page:
    errors.append("运行总览必须保留已确认阻断项的一键受控处理入口")
if "actionAvailable" not in dashboard_page or "autoActionCommand" not in dashboard_page or "securityGroupChecklistText" not in dashboard_page:
    errors.append("运行总览详情必须按真实动作能力保留页面处理、平台服务器兜底和独立安全治理信息")

if "metric-grid" not in dashboard_page or "health-meta" not in dashboard_page or "查看详情" not in dashboard_page:
    errors.append("运行总览首页必须保持核心指标 + 平台状态 + 详情下钻的极简信息层级")
if "自动检测记录" in dashboard_page or "status-chip-grid" in dashboard_page or "pending-box" in dashboard_page:
    errors.append("运行总览首页不得重新铺开检测历史、状态胶囊或待验证明细，避免信息轰炸")
if "nodeVerificationScript" in dashboard_page or "执行节点验证脚本" in dashboard_page or "set -Eeuo pipefail" in dashboard_page:
    errors.append("运行总览不得展示执行节点验证脚本；执行节点验证应放在执行节点接入流程")
if "securityGroupChecklist" not in dashboard_page or "仅供治理参考，不影响运行状态。" not in dashboard_page:
    errors.append("运行总览详情必须把安全组 / 防火墙内容隔离为不影响运行状态的安全治理建议")
if "currentProblems" not in dashboard_page or "['FAIL', 'WARN'].includes(item.status)" not in dashboard_page:
    errors.append("运行总览当前异常必须只聚合已确认 FAIL/WARN，不能把 PENDING 当成待办")
if "slice(0, 4)" not in dashboard_page or "查看全部" not in dashboard_page:
    errors.append("运行总览当前异常必须默认收敛展示，并提供详情下钻而不是一次铺满")
if "normalizePreflightText" not in dashboard_page or "必须处理项" not in dashboard_page:
    errors.append("运行总览历史快照必须对旧文案做展示归一")
if '"PENDING"' not in system_config_service or '"pendingCount"' not in system_config_service or '"verifiedCount"' not in system_config_service:
    errors.append("控制端自动检测缺少 PENDING/已验证计数，未知状态仍可能被误判为运行告警")
if '"AUTO_VERIFY"' not in system_config_service or 'effective_automation_type = "AUTO_VERIFY"' not in system_config_service:
    errors.append("PENDING 必须从后端契约开始归属平台自动验证，不能残留人工处理角色或修复动作")
if '"runtimeEvidence"' not in system_config_service or "_runtime_agent_evidence" not in system_config_service:
    errors.append("控制端自动检测缺少执行节点实时心跳/Docker/digest 运行证据")
if '"securityAdvisories"' not in system_config_service or "security_advisories.append" not in system_config_service:
    errors.append("云侧不可自动读取的安全治理信息必须独立返回，不能混入运行健康检查")
if 'warning_count = sum(1 for item in checks if item["status"] == "WARN")' not in system_config_service:
    errors.append("运行提醒数量必须只统计已确认 WARN，不能统计 PENDING 或安全建议")
if '"readyForRemoteAgent": blocking_count == 0' not in system_config_service:
    errors.append("远程节点接入就绪必须只由已确认阻断项决定，PENDING 不得误阻断")
if "runtimeIssues" not in dashboard_page or "item.status === 'PENDING'" not in dashboard_page or "待自动验证" not in dashboard_page:
    errors.append("运行总览必须分离真实运行异常与待自动验证项，并把待验证明细下沉到详情")
if "configuredDigest" not in system_config_service or "配置中的 digest 仅作为期望值" not in system_config_service:
    errors.append("控制端预检必须把配置 digest 仅作为期望值，不能把配置字符串冒充 Registry/运行证据")
if "平台可一键处理" in dashboard_page or "平台脚本可处理" in dashboard_page:
    errors.append("运行总览不能把脚本兜底能力误展示成页面一键处理能力")
if "impact" not in system_config_service or "verifyCommand" not in system_config_service or "checkSourceLabel" not in system_config_service:
    errors.append("控制端预检缺少影响范围、验证命令或检测来源")
if "automationType" not in system_config_service or "autoActionCommand" not in system_config_service or "prepare-agent-image.sh" not in system_config_service or "actionEndpoint" not in system_config_service:
    errors.append("控制端预检未区分可自动处理项，或未给出 执行组件镜像自动准备动作")
if "platformActionCapability" not in system_config_service or "executionChannel" not in system_config_service or "securityGroupChecklist" not in system_config_service:
    errors.append("控制端预检必须返回平台动作能力、执行通道和安全组规则清单，避免页面动作口径误导")
if "nodeVerificationScript" not in service or "--connect-timeout 3 --max-time 10" not in service or "docker pull" not in service:
    errors.append("执行节点接入流程必须生成带硬超时的目标节点预检脚本，覆盖平台入口、安装脚本、镜像仓库和镜像拉取")
if "--auto-configure-docker-registry" not in text or "insecure-registries" not in text:
    errors.append("Agent 安装脚本缺少授权自动配置 Docker HTTP 私有仓库能力")
if "grep -F '"'"'"$reg"'"'"'" in text or 'grep -F "\\"$reg\\""' not in text:
    errors.append("Agent 安装脚本 Docker insecure-registries 检测必须检查真实 registry 值，不能误查字面量 $reg")
if "--replace-existing-agent" not in text or "CURRENT_STAGE" not in text or "启动 Agent 容器" not in text:
    errors.append("Agent 安装脚本缺少失败阶段标识或已有 Agent 容器替换授权保护")
if "auto_configure_docker_registry" not in service or "replace_existing_agent" not in service:
    errors.append("后端生成的执行节点接入命令缺少显式 Docker registry 授权或重新接入替换控制")
if 'flags.append("--replace-existing-agent")' not in service:
    errors.append("--replace-existing-agent 只能在重新接入场景显式追加，不能作为新增节点默认行为")
if 'flags.append("--auto-configure-docker-registry")' not in service:
    errors.append("Docker insecure-registry 修改必须由显式 auto_configure_docker_registry 授权后才追加到安装命令")
if "执行组件镜像仓库网络检查" not in text or text.index("执行组件镜像仓库网络检查") > text.index("换取执行节点配置"):
    errors.append("Agent 安装脚本必须在消耗一次性接入 Token 前验证 Registry 网络")
if "--max-time" not in text or "docker pull \"$AGENT_IMAGE\" >/dev/null 2>&1" in text:
    errors.append("Agent 安装脚本网络请求必须有硬超时，docker pull 失败不得吞掉原始错误")
if "Docker 已配置并重启，可访问 HTTP 私有仓库" in text:
    errors.append("Docker 重启成功不能冒充 Registry 网络可达")
if "AGENT_DECOMMISSION" not in service or "delete_agent_join_token" not in service:
    errors.append("执行节点清理必须覆盖在线 Agent 退役和孤立接入记录物理清理")
if '"agentDecommission": True' not in agent_main or 'agent.capabilities.get("agentDecommission") is True' not in service:
    errors.append("Agent 远端退役必须由显式 capability 门禁保护，避免旧版 Agent 收到不支持的指令")
if "AGENT_HOST_CONFIG_DIR" not in text or "crawler-agent-host-config" not in text:
    errors.append("新版 Agent 安装必须挂载宿主机配置目录，自动退役后才能清理失效 .env")
if "清理后的记录不再显示" not in frontend or "metricText" not in frontend or "接入中" not in frontend:
    errors.append("执行节点页面必须隐藏清理后的接入记录，并避免未上报资源显示为 0%")
prepare_script = (ROOT / "deploy/scripts/prepare-agent-image.sh").read_text(encoding="utf-8") if (ROOT / "deploy/scripts/prepare-agent-image.sh").exists() else ""
if ".env.tmp_prepare_agent_image" not in prepare_script or "本机 registry 中未发现 crawler_platform_agent" not in prepare_script:
    errors.append("执行组件镜像准备脚本缺少安全 .env 写入或精确 tag 验证")
if "crawler-platform-smoke-registry" not in prepare_script or "REGISTRY_DATA_VOLUME" not in prepare_script or "拒绝把未知容器当成正式 Agent Registry" not in prepare_script:
    errors.append("正式 Agent Registry 必须隔离 smoke 容器，并使用持久化数据卷；历史 smoke registry 只能显式安全接管")
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
print("执行节点接入合约检查通过：节点接入、运行事实自动检测、PENDING 语义和安全治理隔离符合要求。")
