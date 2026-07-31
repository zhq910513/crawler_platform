#!/usr/bin/env bash
set -Eeuo pipefail
# 服务器级 Agent 安装脚本：一台服务器只安装/运行一个 crawler-agent。
# 项目 bootstrap 会优先复用已有 Agent，只有缺失时才提示管理员执行本脚本。
AGENT_HOME="${AGENT_HOME:-/opt/crawler-agent}"
AGENT_STATE_DIR="${AGENT_STATE_DIR:-/var/lib/crawler-agent}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:2.1.0}"
ENV_FILE="${ENV_FILE:-$AGENT_HOME/.env}"
errors=()
warn(){ printf '⚠️  %s\n' "$*"; }
fail(){ errors+=("$*"); }
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then fail "需要 root/sudo 权限安装服务器级 Agent"; fi
if [[ -r /etc/os-release ]]; then . /etc/os-release; [[ "${ID,,}" =~ (centos|rhel|rocky|almalinux) ]] || fail "暂定仅支持 CentOS/RHEL 系系统，当前：${PRETTY_NAME:-unknown}"; else fail "无法读取 /etc/os-release"; fi
command -v docker >/dev/null 2>&1 || fail "Docker 未安装"
if command -v docker >/dev/null 2>&1; then docker info >/dev/null 2>&1 || fail "Docker 服务不可用或当前用户无 Docker 权限"; fi
[[ -f "$ENV_FILE" ]] || fail "Agent 配置文件不存在：$ENV_FILE"
if (( ${#errors[@]} )); then
  echo "❌ Agent 安装预检失败：" >&2
  for item in "${errors[@]}"; do echo " - $item" >&2; done
  exit 1
fi
mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR/runs"
chmod 750 "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_STATE_DIR/runs"
docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent "$AGENT_IMAGE"
echo "✅ crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
