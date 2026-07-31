#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
./deploy/scripts/check-env.sh .env
mkdir -p data/mysql data/redis data/task-logs data/backups /var/lib/crawler-agent/runs /data/crawler-platform/projects
if [[ ! -f agent/.env.local ]]; then
  cat > agent/.env.local <<AGENT_ENV
AGENT_PLATFORM_URL=http://127.0.0.1:${WEB_PORT:-8080}
AGENT_VERIFY_TLS=false
AGENT_AGENT_TOKEN=${AGENT_AGENT_TOKEN:-replace-with-agent-token-from-platform}
AGENT_AGENT_CODE=${AGENT_AGENT_CODE:-agent-local-01}
AGENT_SERVER_CODE=${AGENT_SERVER_CODE:-agent-local-01}
AGENT_AGENT_VERSION=${APP_VERSION:-3.0.0}
AGENT_INSTANCE_ID=
AGENT_MAX_SLOTS=${AGENT_MAX_SLOTS:-2}
AGENT_POLL_INTERVAL_SECONDS=3
AGENT_HEARTBEAT_INTERVAL_SECONDS=15
AGENT_REQUEST_TIMEOUT_SECONDS=15
AGENT_RUN_ROOT=/var/lib/crawler-agent/runs
AGENT_PROJECT_DATA_ROOT=/data/crawler-platform/projects
AGENT_DEFAULT_SHM_SIZE_MB=${AGENT_DEFAULT_SHM_SIZE_MB:-64}
AGENT_PIDS_LIMIT=${AGENT_PIDS_LIMIT:-1024}
AGENT_LOG_MAX_FILE=${AGENT_LOG_MAX_FILE:-3}
AGENT_ENABLE_SHARED_PROJECT_CACHE=true
AGENT_DOCKER_NETWORK=${AGENT_DOCKER_NETWORK:-}
AGENT_READ_ONLY_ROOTFS=false
AGENT_REGISTRY_USERNAME=
AGENT_REGISTRY_PASSWORD=
AGENT_DEFAULT_TIMEOUT_SECONDS=3600
AGENT_CAPABILITIES_JSON=${AGENT_CAPABILITIES_JSON:-{"browser":false,"proxy":false}}
AGENT_ENV
  chmod 600 agent/.env.local
fi
docker compose build api web migrate
docker build -f agent/Dockerfile -t "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION:-3.0.0}}" agent
docker compose up -d mysql redis
docker compose run --rm migrate
docker compose up -d --force-recreate api scheduler maintenance web
docker rm -f "${AGENT_CONTAINER_NAME:-crawler-agent}" >/dev/null 2>&1 || true
docker run -d --name "${AGENT_CONTAINER_NAME:-crawler-agent}" --restart=always --network host --env-file agent/.env.local -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/crawler-agent:/var/lib/crawler-agent -v /data/crawler-platform/projects:/data/crawler-platform/projects "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION:-3.0.0}}"
echo "✅ 单机部署完成：平台 http://127.0.0.1:${WEB_PORT:-8080}，Agent 容器 ${AGENT_CONTAINER_NAME:-crawler-agent} 已启动"
