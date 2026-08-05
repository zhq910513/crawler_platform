#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd 2>/dev/null || pwd)"
if [ -f "$ROOT_DIR/deploy/scripts/lib/host.sh" ]; then . "$ROOT_DIR/deploy/scripts/lib/host.sh"; fi
AGENT_HOME="${AGENT_HOME:-/opt/crawler-agent}"
AGENT_STATE_DIR="${AGENT_STATE_DIR:-/var/lib/crawler-agent}"
AGENT_PROJECT_DATA_ROOT="${AGENT_PROJECT_DATA_ROOT:-/data/crawler-platform/projects}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:1.0.12}"
ENV_FILE="${ENV_FILE:-$AGENT_HOME/.env}"
errors=""
fail(){ errors="$errors\n - $*"; }
[ "$(id -u 2>/dev/null || echo 1)" = "0" ] || fail "建议使用 root/sudo 安装服务器级 Agent；普通用户必须具备 Docker 权限和目录写权限。"
command -v docker >/dev/null 2>&1 || fail "Docker 未安装"
if command -v docker >/dev/null 2>&1; then docker info >/dev/null 2>&1 || fail "Docker 服务不可用或当前用户无 Docker 权限"; fi
[ -f "$ENV_FILE" ] || fail "Agent 配置文件不存在：$ENV_FILE"
if [ -n "$errors" ]; then
  echo "❌ Agent 安装预检失败：" >&2
  printf '%b\n' "$errors" >&2
  exit 1
fi
mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR/runs" "$AGENT_PROJECT_DATA_ROOT"
chmod 750 "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_STATE_DIR/runs" 2>/dev/null || true
docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_DATA_ROOT":/data/crawler-platform/projects "$AGENT_IMAGE"
echo "✅ crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
