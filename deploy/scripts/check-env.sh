#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/.env}"
required=(APP_NAME APP_ENV APP_VERSION DATABASE_URL REDIS_URL JWT_SECRET SECRET_ENCRYPTION_KEY ADMIN_USERNAME ADMIN_PASSWORD)
missing=()
[[ -f "$ENV_FILE" ]] || { echo "❌ 配置文件不存在：$ENV_FILE"; exit 1; }
for key in "${required[@]}"; do
  if ! grep -qE "^${key}=" "$ENV_FILE"; then missing+=("$key"); fi
done
if (( ${#missing[@]} )); then
  echo "❌ .env 缺少配置项：${missing[*]}" >&2
  exit 1
fi
echo "✅ .env 基础配置检查通过：$ENV_FILE"
