#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

ENV_FILE="${1:-.env}"
[ -f "$ENV_FILE" ] || cp_die "配置文件不存在：$ENV_FILE"

set_env_value() {
  local key="$1" value="$2" tmp
  tmp="${ENV_FILE}.tmp_project_build_center.$$"
  awk -v k="$key" -v v="$value" '
    BEGIN { done=0 }
    index($0, k "=") == 1 { print k "=" v; done=1; next }
    { print }
    END { if (!done) print k "=" v }
  ' "$ENV_FILE" > "$tmp" || return 1
  mv "$tmp" "$ENV_FILE"
}

extract_host_from_url() {
  printf '%s' "$1" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^\[([^]]+)\].*$#\1#; s#:([0-9]+)$##'
}

first_host_ip() {
  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1; exit}'
    return 0
  fi
  ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}'
}

registry_port="$(cp_env_value "$ENV_FILE" CRAWLER_AGENT_REGISTRY_PORT)"
registry_port="${registry_port:-5000}"
case "$registry_port" in ''|*[!0-9]*) registry_port="5000" ;; esac

registry_host="$(cp_env_value "$ENV_FILE" CRAWLER_AGENT_REGISTRY_PUBLIC_HOST)"
if [ -z "$registry_host" ]; then
  public_base="$(cp_env_value "$ENV_FILE" CRAWLER_CONTROL_PUBLIC_BASE_URL)"
  public_base="${public_base:-$(cp_env_value "$ENV_FILE" CONTROL_PLANE_PUBLIC_BASE_URL)}"
  if [ -n "$public_base" ]; then
    registry_host="$(extract_host_from_url "$public_base")"
  fi
fi
if [ -z "$registry_host" ] && [ -n "${CP_DEPLOY_PUBLIC_HOST:-}" ]; then
  registry_host="$(extract_host_from_url "$CP_DEPLOY_PUBLIC_HOST")"
fi
if [ -z "$registry_host" ]; then
  registry_host="$(first_host_ip || true)"
fi
if [ -z "$registry_host" ]; then
  registry_host="127.0.0.1"
fi

configured_prefix="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX)"
if [ -z "$configured_prefix" ]; then
  configured_prefix="${registry_host}:${registry_port}/crawler_projects"
fi

set_env_value CRAWLER_PROJECT_BUILD_ENABLED 1
set_env_value CRAWLER_PROJECT_BUILD_ROOT /data/project-builds
set_env_value CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS "$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS || true)"
if [ -z "$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS)" ]; then
  set_env_value CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS 1800
fi
set_env_value CRAWLER_PROJECT_BUILD_STALE_SECONDS "$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_STALE_SECONDS || true)"
if [ -z "$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_STALE_SECONDS)" ]; then
  timeout_seconds="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_TIMEOUT_SECONDS)"
  set_env_value CRAWLER_PROJECT_BUILD_STALE_SECONDS $((timeout_seconds + 60))
fi
set_env_value CRAWLER_PROJECT_BUILD_PLATFORM "${CRAWLER_PROJECT_BUILD_PLATFORM:-$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_PLATFORM)}"
if [ -z "$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_PLATFORM)" ]; then
  set_env_value CRAWLER_PROJECT_BUILD_PLATFORM linux/amd64
fi
pip_index="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_BUILD_PIP_INDEX_URL)"
pip_index="${pip_index:-$(cp_env_value "$ENV_FILE" PIP_INDEX_URL)}"
pip_index="${pip_index:-https://pypi.tuna.tsinghua.edu.cn/simple}"
set_env_value CRAWLER_PROJECT_BUILD_PIP_INDEX_URL "$pip_index"

clone_attempts="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_GIT_CLONE_ATTEMPTS)"
clone_attempts="${clone_attempts:-3}"
case "$clone_attempts" in ''|*[!0-9]*) clone_attempts="3" ;; esac
set_env_value CRAWLER_PROJECT_GIT_CLONE_ATTEMPTS "$clone_attempts"

clone_retry_seconds="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_GIT_CLONE_RETRY_SECONDS)"
clone_retry_seconds="${clone_retry_seconds:-5}"
case "$clone_retry_seconds" in ''|*[!0-9]*) clone_retry_seconds="5" ;; esac
set_env_value CRAWLER_PROJECT_GIT_CLONE_RETRY_SECONDS "$clone_retry_seconds"

clone_timeout_seconds="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_GIT_CLONE_TIMEOUT_SECONDS)"
clone_timeout_seconds="${clone_timeout_seconds:-300}"
case "$clone_timeout_seconds" in ''|*[!0-9]*) clone_timeout_seconds="300" ;; esac
set_env_value CRAWLER_PROJECT_GIT_CLONE_TIMEOUT_SECONDS "$clone_timeout_seconds"

source_archive_fallback="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_SOURCE_ARCHIVE_FALLBACK_ENABLED)"
source_archive_fallback="${source_archive_fallback:-1}"
case "$source_archive_fallback" in 1|true|TRUE|yes|YES|on|ON) source_archive_fallback="1" ;; *) source_archive_fallback="0" ;; esac
set_env_value CRAWLER_PROJECT_SOURCE_ARCHIVE_FALLBACK_ENABLED "$source_archive_fallback"

source_archive_attempts="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_SOURCE_ARCHIVE_ATTEMPTS)"
source_archive_attempts="${source_archive_attempts:-1}"
case "$source_archive_attempts" in ''|*[!0-9]*) source_archive_attempts="1" ;; esac
set_env_value CRAWLER_PROJECT_SOURCE_ARCHIVE_ATTEMPTS "$source_archive_attempts"

source_archive_timeout_seconds="$(cp_env_value "$ENV_FILE" CRAWLER_PROJECT_SOURCE_ARCHIVE_TIMEOUT_SECONDS)"
source_archive_timeout_seconds="${source_archive_timeout_seconds:-120}"
case "$source_archive_timeout_seconds" in ''|*[!0-9]*) source_archive_timeout_seconds="120" ;; esac
set_env_value CRAWLER_PROJECT_SOURCE_ARCHIVE_TIMEOUT_SECONDS "$source_archive_timeout_seconds"

set_env_value CRAWLER_PROJECT_IMAGE_REPOSITORY_PREFIX "$configured_prefix"
set_env_value CRAWLER_AGENT_REGISTRY_PORT "$registry_port"
if [ -z "$(cp_env_value "$ENV_FILE" CRAWLER_AGENT_REGISTRY_PUBLIC_HOST)" ] && [ "$registry_host" != "127.0.0.1" ] && [ "$registry_host" != "localhost" ] && [ "$registry_host" != "0.0.0.0" ]; then
  set_env_value CRAWLER_AGENT_REGISTRY_PUBLIC_HOST "$registry_host"
fi

mkdir -p data/project-builds
chmod 0750 data/project-builds 2>/dev/null || true
cp_info "平台构建中心已自动配置：enabled=1 imagePrefix=${configured_prefix} buildRoot=/data/project-builds"
