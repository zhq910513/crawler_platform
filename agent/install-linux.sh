#!/usr/bin/env bash
set -Eeuo pipefail
# Containerized Agent local installer. It does not require host Python/pip/npm.
AGENT_HOME="${AGENT_HOME:-/opt/crawler-agent}"
AGENT_STATE_DIR="${AGENT_STATE_DIR:-/var/lib/crawler-agent}"
AGENT_PROJECT_DATA_ROOT="${AGENT_PROJECT_DATA_ROOT:-/data/crawler-platform/projects}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
AGENT_VERSION="${AGENT_VERSION:-${AGENT_AGENT_VERSION:-1.1.1}}"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:${AGENT_VERSION}}"
ENV_FILE="${ENV_FILE:-$AGENT_HOME/.env}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

fail(){ echo "[FAIL] $*" >&2; exit 1; }
warn(){ echo "[WARN] $*" >&2; }

if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
  warn "建议使用 root/sudo 安装执行节点服务；普通用户必须具备 Docker 权限和目标目录写权限。"
fi
command -v docker >/dev/null 2>&1 || fail "Docker 未安装。"
docker info >/dev/null 2>&1 || fail "Docker 服务不可用或当前用户无 Docker 权限。"

mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR/runs" "$AGENT_PROJECT_DATA_ROOT"
chmod 750 "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_STATE_DIR/runs" 2>/dev/null || true

if [ ! -f "$ENV_FILE" ]; then
  if [ -f .env.example ]; then
    cp .env.example "$ENV_FILE"
    chmod 0600 "$ENV_FILE" 2>/dev/null || true
    warn "已生成 $ENV_FILE，请填入平台生成的 AGENT_AGENT_TOKEN / AGENT_AGENT_CODE / AGENT_SERVER_CODE 后重新执行。"
    exit 2
  fi
  fail "Agent 配置文件不存在：$ENV_FILE"
fi

if [ -f Dockerfile ] && [ -d crawler_agent ]; then
  docker build --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" --build-arg "AGENT_VERSION=$AGENT_VERSION" --build-arg "APP_GIT_COMMIT=${AGENT_GIT_COMMIT:-unknown}" --build-arg "APP_BUILD_TIME=${AGENT_BUILD_TIME:-unknown}" -f Dockerfile -t "$AGENT_IMAGE" .
fi

if docker ps --filter "label=crawler.platform.run_id" --format '{{.ID}}' | grep -q .; then
  fail "检测到平台任务容器正在运行，拒绝本地替换 Agent。请等待任务结束或先进入维护/Drain。"
fi

backup_name="${AGENT_CONTAINER_NAME}-old-$(date +%Y%m%d%H%M%S)"
had_existing=0
if docker ps -a --format '{{.Names}}' | grep -qx "$AGENT_CONTAINER_NAME"; then
  had_existing=1
  running="$(docker inspect -f '{{.State.Running}}' "$AGENT_CONTAINER_NAME" 2>/dev/null || echo false)"
  [ "$running" != "true" ] || docker stop -t 20 "$AGENT_CONTAINER_NAME" >/dev/null || fail "无法停止旧 Agent 容器。"
  docker rename "$AGENT_CONTAINER_NAME" "$backup_name" >/dev/null || fail "无法保留旧 Agent 容器副本。"
fi

if docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_DATA_ROOT":/data/crawler-platform/projects "$AGENT_IMAGE" >/dev/null; then
  sleep 3
  if [ "$(docker inspect -f '{{.State.Running}}' "$AGENT_CONTAINER_NAME" 2>/dev/null || echo false)" = "true" ]; then
    [ "$had_existing" = "0" ] || docker rm -f "$backup_name" >/dev/null 2>&1 || warn "旧 Agent 副本清理失败：$backup_name"
    echo "✅ crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
    exit 0
  fi
fi

docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
if [ "$had_existing" = "1" ]; then
  docker rename "$backup_name" "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
  docker start "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
  warn "新 Agent 启动失败，已尝试恢复旧 Agent 容器：$AGENT_CONTAINER_NAME"
fi
fail "crawler-agent 启动失败。"
