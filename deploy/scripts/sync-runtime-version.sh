#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

release_env="$(bash deploy/scripts/resolve-release-version.sh --export)"
eval "$release_env"
: "${RELEASE_VERSION:?}"
: "${RELEASE_GIT_COMMIT:?}"

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    cp_warn ".env 不存在，已从 .env.example 初始化；请确认生产密钥已替换。"
  else
    cp_die ".env 不存在，且找不到 .env.example。"
    exit 1
  fi
fi

backup=".env.bak_$(date '+%Y%m%d_%H%M%S')"
cp .env "$backup"

set_env_key() {
  local key="$1" value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '\n%s=%s\n' "$key" "$value" >> .env
  fi
}

build_time="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
set_env_key APP_VERSION "$RELEASE_VERSION"
set_env_key PLATFORM_IMAGE_TAG "$RELEASE_VERSION"
set_env_key APP_GIT_COMMIT "$RELEASE_GIT_COMMIT"
set_env_key APP_BUILD_TIME "$build_time"

cp_info "运行版本已同步：version=${RELEASE_VERSION} source=${RELEASE_VERSION_SOURCE:-unknown} gitCommit=${RELEASE_GIT_COMMIT} buildTime=${build_time}"
cp_info ".env 已备份：${backup}"
