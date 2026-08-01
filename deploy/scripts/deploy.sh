#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics
./deploy/scripts/prepare.sh
cp_require_docker
cp_warn_cn_mirrors

MYSQL_ID=$(cp_compose ps -q mysql 2>/dev/null || true)
if [ -n "$MYSQL_ID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$MYSQL_ID" 2>/dev/null || true)" = "true" ] && [ "${SKIP_BACKUP:-0}" != "1" ]; then
  ./deploy/scripts/backup.sh
fi

if [ "${NO_CACHE:-0}" = "1" ]; then
  cp_compose build --progress=plain --no-cache
else
  cp_compose build --progress=plain
fi
cp_compose up -d mysql redis
cp_compose run --rm migrate
cp_compose up -d --force-recreate api scheduler maintenance web

PORT="$(cp_env_value .env WEB_PORT)"; PORT="${PORT:-8080}"
if cp_wait_http "http://127.0.0.1:${PORT}/health" 120 2; then
  cp_compose ps
  echo "crawler_platform 部署完成：http://服务器IP:${PORT}"
  exit 0
fi
cp_compose ps
cp_compose logs --tail=200 api web
cp_die "部署后健康检查失败。"
