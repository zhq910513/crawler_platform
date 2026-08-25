#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
. "$ROOT_DIR/deploy/scripts/lib/version.sh"
cd "$ROOT_DIR"

release_env="$(cp_resolve_release_version)"
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
# Agent 版本独立于平台版本；平台 patch 不再改写 AGENT_AGENT_VERSION。
agent_version="$(cp_env_value .env AGENT_AGENT_VERSION)"
agent_version="${agent_version:-1.1.2}"
set_env_key AGENT_AGENT_VERSION "$agent_version"
bash deploy/scripts/configure-project-build-center.sh .env

mkdir -p .release
cp_runtime_metadata_json "crawler_platform" "$RELEASE_VERSION" "$RELEASE_GIT_COMMIT" "$build_time" > .release/version.json
cat > .release/version.env <<EOF_ENV
APP_VERSION=$RELEASE_VERSION
PLATFORM_IMAGE_TAG=$RELEASE_VERSION
APP_GIT_COMMIT=$RELEASE_GIT_COMMIT
APP_BUILD_TIME=$build_time
AGENT_AGENT_VERSION=$agent_version
EOF_ENV

cp_info "运行版本已同步：version=${RELEASE_VERSION} source=${RELEASE_VERSION_SOURCE:-unknown} gitCommit=${RELEASE_GIT_COMMIT} buildTime=${build_time}"
cp_info ".env 已备份：${backup}"
cp_info "公共发布元数据已生成：.release/version.json"
