#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

cp_fix_project_permissions || true
cp_require_docker

release_env="$(bash deploy/scripts/resolve-release-version.sh --export)"
eval "$release_env"
cp_info "开始发布升级：version=${RELEASE_VERSION} source=${RELEASE_VERSION_SOURCE} gitCommit=${RELEASE_GIT_COMMIT}"

bash deploy/scripts/sync-runtime-version.sh
bash deploy/scripts/doctor.sh
bash deploy/scripts/commercial-release-gate.sh
bash deploy/scripts/backup.sh
bash deploy/scripts/migrate-database.sh

cp_info "构建并启动业务服务。"
cp_compose build migrate api scheduler maintenance web
cp_compose up -d migrate api scheduler maintenance web

cp_info "等待 API 健康检查。"
for i in $(seq 1 60); do
  health_json="$(cp_compose exec -T api sh -lc 'api_port="${API_INTERNAL_PORT:-8000}"; curl -fsS "http://127.0.0.1:${api_port}/health"' 2>/dev/null || true)"
  if printf '%s' "$health_json" | grep -q '"status":"ok"'; then
    break
  fi
  sleep 2
  if [ "$i" = "60" ]; then
    cp_print_diagnostics || true
    cp_die "API 健康检查超时。"
    exit 1
  fi
done

printf '%s\n' "$health_json"
if ! printf '%s' "$health_json" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"$RELEASE_VERSION"'"'; then
  cp_print_diagnostics || true
  cp_die "/health 版本与发布版本不一致，期望 ${RELEASE_VERSION}。"
  exit 1
fi
if ! printf '%s' "$health_json" | grep -Eq '"gitCommit"[[:space:]]*:[[:space:]]*"'"$RELEASE_GIT_COMMIT"'"'; then
  cp_warn "/health gitCommit 与当前 Git commit 不一致；请确认镜像是否完成重建。"
fi

web_port="$(cp_env_value .env WEB_PORT)"
web_port="${web_port:-80}"
cp_info "校验前端版本文件 /version.json。"
version_json=""
for i in $(seq 1 30); do
  version_json="$(cp_curl_tool -fsS "http://127.0.0.1:${web_port}/version.json" 2>/dev/null || true)"
  if printf '%s' "$version_json" | grep -q '"appName"'; then
    break
  fi
  sleep 2
done
printf '%s\n' "$version_json"
if ! printf '%s' "$version_json" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"$RELEASE_VERSION"'"'; then
  cp_print_diagnostics || true
  cp_die "/version.json 版本与发布版本不一致，期望 ${RELEASE_VERSION}。"
  exit 1
fi
if ! printf '%s' "$version_json" | grep -Eq '"gitCommit"[[:space:]]*:[[:space:]]*"'"$RELEASE_GIT_COMMIT"'"'; then
  cp_warn "/version.json gitCommit 与当前 Git commit 不一致；请确认 web 镜像是否完成重建。"
fi

if [ "${AUTO_PREPARE_AGENT_IMAGE:-1}" = "1" ]; then
  cp_info "部署后自动准备 Agent 镜像分发。"
  if ! bash deploy/scripts/prepare-agent-image.sh --version "$RELEASE_VERSION"; then
    if [ "${STRICT_AGENT_IMAGE_PREPARE:-0}" = "1" ]; then
      cp_die "Agent 镜像自动准备失败，STRICT_AGENT_IMAGE_PREPARE=1 已阻断发布升级。"
    fi
    cp_warn "Agent 镜像自动准备未完成；请到运行总览查看平台自检并按提示处理。"
  fi
fi

bash deploy/scripts/record-platform-preflight-snapshot.sh DEPLOY || true
cp_info "发布升级完成：RELEASE_UPGRADE=PASS version=${RELEASE_VERSION}"
