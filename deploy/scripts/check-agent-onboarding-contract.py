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
companies = (ROOT / "frontend/src/views/CompaniesPage.vue").read_text(encoding="utf-8")

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
if "远程服务器不能使用本机地址" not in frontend or "connectivityCommand" not in frontend:
    errors.append("执行节点接入前端缺少远程地址拦截或连通性验证命令")
legacy_token_text = "生成" + "接入" + "凭证"
if legacy_token_text in companies:
    errors.append("公司页面仍使用含糊的“" + legacy_token_text + "”文案")
if "项目发布凭证" in companies:
    errors.append("项目发布凭证不应继续放在公司管理页面")
if "配置助手" not in companies:
    errors.append("公司页面缺少配置助手入口")

if errors:
    print("执行节点接入合约检查失败：", file=sys.stderr)
    for item in errors:
        print("- " + item, file=sys.stderr)
    sys.exit(1)
print("执行节点接入合约检查通过：安装脚本、控制端地址、配置助手和前端向导符合要求。")
