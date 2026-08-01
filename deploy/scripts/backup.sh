#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker
mkdir -p data/backups
MYSQL_ID=$(cp_compose ps -q mysql 2>/dev/null || true)
if [ -z "$MYSQL_ID" ] || [ "$(docker inspect -f '{{.State.Running}}' "$MYSQL_ID" 2>/dev/null || true)" != "true" ]; then
  echo "MySQL 容器未运行，无法备份。" >&2
  exit 2
fi
FILE="data/backups/crawler_platform_$(date +%Y%m%d_%H%M%S).sql.gz"
cp_compose exec -T mysql sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --quick --routines --triggers --events --set-gtid-purged=OFF "$MYSQL_DATABASE"' | gzip -9 > "$FILE"
test -s "$FILE"
find data/backups -type f -name '*.sql.gz' -mtime +30 -delete
 echo "备份完成：$FILE"
