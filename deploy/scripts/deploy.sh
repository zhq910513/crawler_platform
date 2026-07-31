#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
./deploy/scripts/prepare.sh

MYSQL_ID=$(docker compose ps -q mysql 2>/dev/null || true)
if [[ -n "$MYSQL_ID" && "$(docker inspect -f '{{.State.Running}}' "$MYSQL_ID" 2>/dev/null || true)" == "true" && "${SKIP_BACKUP:-0}" != "1" ]]; then
  ./deploy/scripts/backup.sh
fi

BUILD_ARGS=(build --progress=plain)
if [[ "${NO_CACHE:-0}" == "1" ]]; then
  BUILD_ARGS+=(--no-cache)
fi
docker compose "${BUILD_ARGS[@]}"
docker compose up -d mysql redis
docker compose run --rm migrate
docker compose up -d --force-recreate api scheduler maintenance web

PORT=$(awk -F= '/^WEB_PORT=/{print $2}' .env | tail -1)
PORT=${PORT:-8080}
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null; then
    docker compose ps
    echo "crawler_platform 部署完成：http://服务器IP:${PORT}"
    exit 0
  fi
  sleep 2
done
docker compose ps
docker compose logs --tail=200 api web
echo "部署后健康检查失败。" >&2
exit 1
