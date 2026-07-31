#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
./deploy/scripts/check-env.sh .env
mkdir -p data/mysql data/redis data/task-logs data/backups /var/lib/crawler-agent/runs
if [[ ! -f agent/.env.local ]]; then
  cat > agent/.env.local <<AGENT_ENV
PLATFORM_URL=http://127.0.0.1:${WEB_PORT:-8080}
PLATFORM_VERIFY_TLS=false
AGENT_ALLOW_INSECURE_HTTP=true
AGENT_BOOTSTRAP_TOKEN=${AGENT_BOOTSTRAP_TOKEN:-change-this-agent-bootstrap-token}
AGENT_CODE=${AGENT_CODE:-agent-local-01}
SERVER_CODE=${SERVER_CODE:-agent-local-01}
SERVER_NAME=${SERVER_NAME:-本机Agent}
AGENT_VERSION=${APP_VERSION:-2.1.0}
AGENT_INSTANCE_ID=
AGENT_MAX_SLOTS=${AGENT_MAX_SLOTS:-2}
AGENT_CAPABILITIES=["api","browser"]
AGENT_LABELS={"mode":"single-server"}
AGENT_HEARTBEAT_SECONDS=15
AGENT_CLAIM_SECONDS=3
AGENT_RUN_HEARTBEAT_SECONDS=10
AGENT_REQUEST_TIMEOUT_SECONDS=15
AGENT_RUN_ROOT=/var/lib/crawler-agent/runs
AGENT_LOG_UPLOAD_BATCH_SIZE=200
AGENT_EVENT_UPLOAD_BATCH_SIZE=100
AGENT_RECOVERY_SCAN_SECONDS=10
AGENT_COMPLETED_RETENTION_HOURS=72
CRAWLER_CONTAINER_UID=10001
CRAWLER_CONTAINER_GID=10001
AGENT_CONTAINER_NETWORK=bridge
DOCKER_REGISTRY_USERNAME=
DOCKER_REGISTRY_PASSWORD=
AGENT_ENV
  chmod 600 agent/.env.local
fi
docker compose build api web migrate
docker build -f agent/Dockerfile -t "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION:-2.1.0}}" agent
docker compose up -d mysql redis
docker compose run --rm migrate
docker compose up -d --force-recreate api scheduler maintenance web
docker rm -f "${AGENT_CONTAINER_NAME:-crawler-agent}" >/dev/null 2>&1 || true
docker run -d --name "${AGENT_CONTAINER_NAME:-crawler-agent}" --restart=always --network host --env-file agent/.env.local -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/crawler-agent:/var/lib/crawler-agent "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION:-2.1.0}}"
echo "✅ 单机部署完成：平台 http://127.0.0.1:${WEB_PORT:-8080}，Agent 容器 ${AGENT_CONTAINER_NAME:-crawler-agent} 已启动"
