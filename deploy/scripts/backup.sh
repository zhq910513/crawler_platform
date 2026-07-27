#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a
source .env
set +a
mkdir -p data/backups
FILE="data/backups/crawler_platform_$(date +%Y%m%d_%H%M%S).sql.gz"
docker compose exec -T mysql mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE" | gzip > "$FILE"
find data/backups -type f -name '*.sql.gz' -mtime +30 -delete
echo "Backup created: $FILE"
