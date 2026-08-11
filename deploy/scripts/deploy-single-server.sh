#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics
./deploy/scripts/doctor.sh
./deploy/scripts/check-env.sh .env
cp_require_docker
cp_warn_cn_mirrors
mkdir -p data/mysql data/redis data/task-logs data/backups
if cp_has_sudo; then
  cp_sudo mkdir -p /var/lib/crawler-agent/runs /data/crawler-platform/projects
else
  mkdir -p /var/lib/crawler-agent/runs /data/crawler-platform/projects 2>/dev/null || cp_die "无法创建 Agent 数据目录，请使用 root/sudo。"
fi
APP_VERSION_VALUE="$(cp_env_value .env APP_VERSION)"; APP_VERSION_VALUE="${APP_VERSION_VALUE:-1.0.32}"
WEB_PORT_VALUE="$(cp_env_value .env WEB_PORT)"; WEB_PORT_VALUE="${WEB_PORT_VALUE:-8080}"
if [ ! -f agent/.env.local ]; then
  cat > agent/.env.local <<AGENT_ENV
AGENT_PLATFORM_URL=http://127.0.0.1:${WEB_PORT_VALUE}
AGENT_VERIFY_TLS=false
AGENT_AGENT_TOKEN=${AGENT_AGENT_TOKEN:-replace-with-agent-token-from-platform}
AGENT_AGENT_CODE=${AGENT_AGENT_CODE:-agent-local-01}
AGENT_SERVER_CODE=${AGENT_SERVER_CODE:-agent-local-01}
AGENT_AGENT_VERSION=${APP_VERSION_VALUE}
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
cp_compose build api web migrate
docker build --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" --build-arg "APP_VERSION=${APP_VERSION_VALUE}" --build-arg "APP_GIT_COMMIT=$(cp_env_value .env APP_GIT_COMMIT)" --build-arg "APP_BUILD_TIME=$(cp_env_value .env APP_BUILD_TIME)" -f agent/Dockerfile -t "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION_VALUE}}" agent
cp_compose up -d mysql redis
cp_compose run --rm migrate
cp_compose up -d --force-recreate api scheduler maintenance web
docker rm -f "${AGENT_CONTAINER_NAME:-crawler-agent}" >/dev/null 2>&1 || true
docker run -d --name "${AGENT_CONTAINER_NAME:-crawler-agent}" --restart=always --network host --env-file agent/.env.local -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/crawler-agent:/var/lib/crawler-agent -v /data/crawler-platform/projects:/data/crawler-platform/projects "${AGENT_IMAGE:-crawler_platform_agent:${APP_VERSION_VALUE}}"
echo "✅ 单机部署完成：平台 http://127.0.0.1:${WEB_PORT_VALUE}，Agent 容器 ${AGENT_CONTAINER_NAME:-crawler-agent} 已启动"
