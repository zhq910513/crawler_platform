#!/usr/bin/env bash
set -Eeuo pipefail
# Containerized Agent installer. It does not require host Python/pip/npm.
AGENT_HOME="${AGENT_HOME:-/opt/crawler-agent}"
AGENT_STATE_DIR="${AGENT_STATE_DIR:-/var/lib/crawler-agent}"
AGENT_PROJECT_DATA_ROOT="${AGENT_PROJECT_DATA_ROOT:-/data/crawler-platform/projects}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
AGENT_VERSION="${AGENT_VERSION:-${AGENT_AGENT_VERSION:-1.0.70}}"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:${AGENT_VERSION}}"
ENV_FILE="${ENV_FILE:-$AGENT_HOME/.env}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
  echo "建议使用 root/sudo 安装执行节点服务；普通用户必须具备 Docker 权限和目标目录写权限。" >&2
fi
command -v docker >/dev/null 2>&1 || { echo "Docker 未安装。" >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker 服务不可用或当前用户无 Docker 权限。" >&2; exit 1; }

mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR/runs" "$AGENT_PROJECT_DATA_ROOT"
chmod 750 "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_STATE_DIR/runs" 2>/dev/null || true

if [ ! -f "$ENV_FILE" ]; then
  if [ -f .env.example ]; then
    cp .env.example "$ENV_FILE"
    chmod 0600 "$ENV_FILE" 2>/dev/null || true
    echo "已生成 $ENV_FILE，请填入平台生成的 AGENT_AGENT_TOKEN / AGENT_AGENT_CODE / AGENT_SERVER_CODE 后重新执行。" >&2
    exit 2
  fi
  echo "Agent 配置文件不存在：$ENV_FILE" >&2
  exit 1
fi

if [ -f Dockerfile ] && [ -d crawler_agent ]; then
  docker build --build-arg "PIP_INDEX_URL=$PIP_INDEX_URL" --build-arg "APP_VERSION=$AGENT_VERSION" --build-arg "APP_GIT_COMMIT=${AGENT_GIT_COMMIT:-unknown}" --build-arg "APP_BUILD_TIME=${AGENT_BUILD_TIME:-unknown}" -f Dockerfile -t "$AGENT_IMAGE" .
fi

docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_DATA_ROOT":/data/crawler-platform/projects "$AGENT_IMAGE"
echo "✅ crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
