#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
ENV_FILE="${1:-$ROOT_DIR/.env}"

required="APP_NAME APP_ENV APP_VERSION PLATFORM_IMAGE_TAG DATABASE_URL REDIS_URL JWT_SECRET SECRET_ENCRYPTION_KEY ADMIN_USERNAME ADMIN_PASSWORD MYSQL_ROOT_PASSWORD MYSQL_PASSWORD REDIS_PASSWORD PIP_INDEX_URL NPM_REGISTRY"
missing=""
[ -f "$ENV_FILE" ] || { echo "❌ 配置文件不存在：$ENV_FILE" >&2; exit 1; }
for key in $required; do
  if ! grep -qE "^${key}=" "$ENV_FILE"; then missing="$missing $key"; fi
done
if [ -n "$missing" ]; then
  echo "❌ .env 缺少配置项：$missing" >&2
  exit 1
fi

app_version="$(cp_env_value "$ENV_FILE" APP_VERSION)"
tag_version="$(cp_env_value "$ENV_FILE" PLATFORM_IMAGE_TAG)"
if [ "$app_version" != "$tag_version" ]; then
  echo "❌ APP_VERSION 与 PLATFORM_IMAGE_TAG 不一致：$app_version / $tag_version" >&2
  exit 1
fi
if [ "$app_version" != "1.0.25" ]; then
  echo "⚠️  当前 APP_VERSION=$app_version；本次发布应统一为 1.0.25。" >&2
fi

if grep -qE 'ReplaceWith|change-this|Admin@123456' "$ENV_FILE"; then
  echo "❌ .env 仍包含占位弱配置，请先生成或替换强密码。" >&2
  exit 1
fi

if ! grep -q '^DOCKER_REGISTRY_MIRRORS=' "$ENV_FILE"; then
  echo "⚠️  .env 未配置 DOCKER_REGISTRY_MIRRORS。国内服务器建议执行 ./deploy/scripts/prepare-cn-mirrors.sh --yes" >&2
fi

echo "✅ .env 基础配置检查通过：$ENV_FILE"
