#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

release_env="$(bash deploy/scripts/resolve-release-version.sh --export)"
eval "$release_env"
: "${RELEASE_VERSION:?}"

failures=0
warnings=0
fail() { cp_error "$*"; failures=$((failures + 1)); }
warn() { cp_warn "$*"; warnings=$((warnings + 1)); }

if [ ! -f .env ]; then
  fail ".env 不存在，无法确认运行版本。"
else
  app_version="$(cp_env_value .env APP_VERSION)"
  image_tag="$(cp_env_value .env PLATFORM_IMAGE_TAG)"
  [ "$app_version" = "$RELEASE_VERSION" ] || fail ".env APP_VERSION=${app_version:-<empty>}，期望 ${RELEASE_VERSION}。请执行：bash deploy/scripts/sync-runtime-version.sh"
  [ "$image_tag" = "$RELEASE_VERSION" ] || fail ".env PLATFORM_IMAGE_TAG=${image_tag:-<empty>}，期望 ${RELEASE_VERSION}。请执行：bash deploy/scripts/sync-runtime-version.sh"
fi

if [ -f VERSION ]; then
  version_file="$(tr -d '[:space:]' < VERSION)"
  [ "$version_file" = "$RELEASE_VERSION" ] || warn "VERSION=${version_file} 与当前发布版本 ${RELEASE_VERSION} 不一致；发布版本来源=${RELEASE_VERSION_SOURCE:-unknown}。"
fi

if [ -f frontend/package.json ]; then
  frontend_version="$(sed -nE 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' frontend/package.json | head -n 1)"
  [ -z "$frontend_version" ] || [ "$frontend_version" = "$RELEASE_VERSION" ] || warn "frontend/package.json version=${frontend_version} 与当前发布版本 ${RELEASE_VERSION} 不一致；前端运行版本以后端 /health 为准。"
fi

if [ -f backend/app/config.py ]; then
  backend_default="$(sed -nE 's/^[[:space:]]*app_version:[^=]*=[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' backend/app/config.py | head -n 1)"
  [ -z "$backend_default" ] || [ "$backend_default" = "$RELEASE_VERSION" ] || warn "backend 默认 app_version=${backend_default} 与当前发布版本 ${RELEASE_VERSION} 不一致；生产运行以 .env APP_VERSION 为准。"
fi

if [ -f agent/crawler_agent/__init__.py ]; then
  agent_version="$(sed -nE 's/^__version__[[:space:]]*=[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)"/\1/p' agent/crawler_agent/__init__.py | head -n 1)"
  [ -z "$agent_version" ] || [ "$agent_version" = "$RELEASE_VERSION" ] || warn "agent __version__=${agent_version} 与当前发布版本 ${RELEASE_VERSION} 不一致；Agent 镜像 tag 以发布版本为准。"
fi

if grep -R "crawler_platform_.*:1\.0\.1" -n docker-compose.yml deploy/compose 2>/dev/null; then
  fail "Compose 文件仍存在写死的 1.0.1 镜像标签。"
fi

if [ "$failures" -gt 0 ]; then
  echo "VERSION_CONSISTENCY=FAIL failures=${failures} warnings=${warnings}" >&2
  exit 1
fi

echo "版本一致性检查通过：releaseVersion=${RELEASE_VERSION} source=${RELEASE_VERSION_SOURCE:-unknown} warnings=${warnings}"
