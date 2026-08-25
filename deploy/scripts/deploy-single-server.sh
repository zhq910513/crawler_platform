#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics
bash deploy/scripts/doctor.sh
bash deploy/scripts/check-env.sh .env
cp_require_docker
cp_warn_cn_mirrors
mkdir -p data/mysql data/redis data/task-logs data/backups
if cp_has_sudo; then
  cp_sudo mkdir -p /var/lib/crawler-agent/runs /data/crawler-platform/projects
else
  mkdir -p /var/lib/crawler-agent/runs /data/crawler-platform/projects 2>/dev/null || cp_die "无法创建 Agent 数据目录，请使用 root/sudo。"
fi
APP_VERSION_VALUE="$(cp_env_value .env APP_VERSION)"; APP_VERSION_VALUE="${APP_VERSION_VALUE:-1.0.91}"
AGENT_VERSION_VALUE="$(cp_env_value .env AGENT_AGENT_VERSION)"; AGENT_VERSION_VALUE="${AGENT_VERSION_VALUE:-1.1.2}"
WEB_PORT_VALUE="$(cp_env_value .env WEB_PORT)"; WEB_PORT_VALUE="${WEB_PORT_VALUE:-80}"
AGENT_IMAGE_VALUE="${AGENT_IMAGE:-crawler_platform_agent:${AGENT_VERSION_VALUE}}"
if [ ! -f agent/.env.local ]; then
  cat > agent/.env.local <<AGENT_ENV
AGENT_CONTROL_PLANE_URL=http://127.0.0.1:${WEB_PORT_VALUE}
AGENT_VERIFY_TLS=false
AGENT_AGENT_TOKEN=${AGENT_AGENT_TOKEN:-replace-with-agent-token-from-platform}
AGENT_AGENT_CODE=${AGENT_AGENT_CODE:-agent-local-01}
AGENT_SERVER_CODE=${AGENT_SERVER_CODE:-agent-local-01}
AGENT_AGENT_VERSION=${AGENT_VERSION_VALUE}
AGENT_IMAGE=${AGENT_IMAGE_VALUE}
AGENT_EXPECTED_IMAGE_DIGEST=
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
cp_compose up -d mysql redis
cp_compose run --rm migrate
cp_compose up -d --force-recreate api scheduler maintenance web
if ! docker image inspect "$AGENT_IMAGE_VALUE" >/dev/null 2>&1; then
  cp_info "本地 Agent 镜像不存在，按独立 Agent 版本构建：$AGENT_IMAGE_VALUE"
  docker build \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
    --build-arg "AGENT_VERSION=${AGENT_VERSION_VALUE}" \
    --build-arg "APP_GIT_COMMIT=$(cp_env_value .env APP_GIT_COMMIT)" \
    --build-arg "APP_BUILD_TIME=$(cp_env_value .env APP_BUILD_TIME)" \
    -f agent/Dockerfile -t "$AGENT_IMAGE_VALUE" agent
else
  cp_info "本地 Agent 镜像已存在，普通平台发布不重建 Agent：$AGENT_IMAGE_VALUE"
fi
if [ "${AUTO_PREPARE_AGENT_IMAGE:-0}" = "1" ]; then
  if ! bash deploy/scripts/prepare-agent-image.sh; then
    if [ "${STRICT_AGENT_IMAGE_PREPARE:-0}" = "1" ]; then
      cp_die "执行组件镜像自动准备失败，STRICT_AGENT_IMAGE_PREPARE=1 已阻断单机部署。"
    fi
    cp_warn "执行组件镜像自动准备未完成；单机本地执行组件仍可使用本地构建镜像。"
  fi
else
  cp_info "普通平台发布跳过 Agent 镜像准备；如 Agent 独立版本变化，请显式设置 AUTO_PREPARE_AGENT_IMAGE=1。"
fi
agent_container="${AGENT_CONTAINER_NAME:-crawler-agent}"
if docker ps -a --filter "name=^/${agent_container}$" --format '{{.Names}}' | grep -Fx "$agent_container" >/dev/null 2>&1; then
  existing_image="$(docker inspect -f '{{.Config.Image}}' "$agent_container" 2>/dev/null || true)"
  if [ "$existing_image" = "$AGENT_IMAGE_VALUE" ]; then
    cp_info "Agent 容器已存在且镜像未变化，普通平台发布不重启 Agent：$agent_container"
  elif [ "${FORCE_RECREATE_LOCAL_AGENT:-0}" = "1" ]; then
    backup_name="${agent_container}-old-$(date +%Y%m%d%H%M%S)"
    docker stop -t 20 "$agent_container" >/dev/null || true
    docker rename "$agent_container" "$backup_name" >/dev/null
    if docker run -d --name "$agent_container" --restart=always --network host --env-file agent/.env.local -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/crawler-agent:/var/lib/crawler-agent -v /data/crawler-platform/projects:/data/crawler-platform/projects "$AGENT_IMAGE_VALUE" >/dev/null; then
      sleep 3
      if [ "$(docker inspect -f '{{.State.Running}}' "$agent_container" 2>/dev/null || echo false)" = "true" ]; then
        docker rm -f "$backup_name" >/dev/null 2>&1 || true
      else
        docker rm -f "$agent_container" >/dev/null 2>&1 || true
        docker rename "$backup_name" "$agent_container" >/dev/null 2>&1 || true
        docker start "$agent_container" >/dev/null 2>&1 || true
        cp_die "新 Agent 容器启动后未保持运行，已尝试恢复旧容器。"
      fi
    else
      docker rename "$backup_name" "$agent_container" >/dev/null 2>&1 || true
      docker start "$agent_container" >/dev/null 2>&1 || true
      cp_die "新 Agent 容器启动失败，已尝试恢复旧容器。"
    fi
  else
    cp_warn "Agent 容器已存在且镜像不同，普通平台发布不替换 Agent。需要迁移时请通过执行节点页面或设置 FORCE_RECREATE_LOCAL_AGENT=1。"
  fi
else
  docker run -d --name "$agent_container" --restart=always --network host --env-file agent/.env.local -v /var/run/docker.sock:/var/run/docker.sock -v /var/lib/crawler-agent:/var/lib/crawler-agent -v /data/crawler-platform/projects:/data/crawler-platform/projects "$AGENT_IMAGE_VALUE"
fi
bash deploy/scripts/record-platform-preflight-snapshot.sh DEPLOY || true
echo "✅ 单机部署完成：平台 http://127.0.0.1:${WEB_PORT_VALUE}，Agent 容器 ${agent_container} 已按独立生命周期处理"
