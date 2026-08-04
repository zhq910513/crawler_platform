#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
. "$ROOT_DIR/deploy/scripts/lib/version.sh"
cd "$ROOT_DIR"

release_env="$(cp_resolve_release_version)"
eval "$release_env"
: "${RELEASE_VERSION:?}"

failures=0
warnings=0
fail() { cp_error "$*"; failures=$((failures + 1)); }
warn() { cp_warn "$*"; warnings=$((warnings + 1)); }
info() { cp_info "$*"; }

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
  if [ "$version_file" != "$RELEASE_VERSION" ]; then
    warn "VERSION=${version_file} 与当前发布版本 ${RELEASE_VERSION} 不一致；发布版本来源=${RELEASE_VERSION_SOURCE:-unknown}。VERSION 仅作为无 Git 版本信息时的 fallback。"
  fi
fi

if [ -f deploy/scripts/lib/version.sh ] && grep -q 'cp_resolve_release_version' deploy/scripts/lib/version.sh; then
  info "公共 Shell 版本模块存在：deploy/scripts/lib/version.sh"
else
  fail "缺少公共 Shell 版本模块 deploy/scripts/lib/version.sh。"
fi

if [ -f backend/app/version.py ] && grep -q 'def release_metadata' backend/app/version.py && grep -q 'default_version' backend/app/config.py; then
  info "后端使用公共运行版本适配器：backend/app/version.py"
else
  fail "后端未接入公共运行版本适配器。"
fi

if [ -f agent/crawler_agent/version.py ] && grep -q 'def release_metadata' agent/crawler_agent/version.py && grep -q 'default_version' agent/crawler_agent/config.py; then
  info "Agent 使用公共运行版本适配器：agent/crawler_agent/version.py"
else
  fail "Agent 未接入公共运行版本适配器。"
fi

if [ -f frontend/src/config/version.ts ] && grep -q 'VITE_APP_VERSION' frontend/src/config/version.ts && grep -q 'version.json' frontend/Dockerfile; then
  info "前端使用构建注入版本与 /version.json。"
else
  fail "前端未接入构建注入版本与 /version.json。"
fi

if grep -q 'npm version "\$APP_VERSION"' frontend/Dockerfile 2>/dev/null; then
  copy_line="$(grep -n '^COPY \. \.' frontend/Dockerfile | tail -n 1 | cut -d: -f1 || true)"
  version_line="$(grep -n 'npm version "\$APP_VERSION"' frontend/Dockerfile | tail -n 1 | cut -d: -f1 || true)"
  if [ -n "$copy_line" ] && [ -n "$version_line" ] && [ "$version_line" -gt "$copy_line" ]; then
    info "前端 package.json 构建版本会在 COPY . . 后注入，避免被源码覆盖。"
  else
    fail "frontend/Dockerfile 中 npm version 必须在 COPY . . 之后执行。"
  fi
else
  fail "frontend/Dockerfile 未检测到 npm version APP_VERSION 注入。"
fi

if [ -f frontend/package.json ]; then
  frontend_version="$(sed -nE 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"([0-9]+\.[0-9]+\.[0-9]+)".*/\1/p' frontend/package.json | head -n 1)"
  [ -z "$frontend_version" ] || info "frontend/package.json baseline=${frontend_version}；Docker 构建时统一注入发布版本 ${RELEASE_VERSION}。"
fi

if grep -R -E "crawler_platform_.*:1\.0\.1([^0-9.]|$)" -n docker-compose.yml deploy/compose 2>/dev/null; then
  fail "Compose 文件仍存在写死的 1.0.1 镜像标签。"
fi

if [ "$failures" -gt 0 ]; then
  echo "VERSION_CONSISTENCY=FAIL failures=${failures} warnings=${warnings}" >&2
  exit 1
fi

echo "版本一致性检查通过：releaseVersion=${RELEASE_VERSION} source=${RELEASE_VERSION_SOURCE:-unknown} warnings=${warnings}"
