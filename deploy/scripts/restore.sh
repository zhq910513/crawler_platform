#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
FILE=${1:-}
if [[ -z "$FILE" || ! -f "$FILE" ]]; then
  echo "用法：$0 data/backups/xxx.sql.gz" >&2
  exit 2
fi
read -r -p "将覆盖当前 crawler_platform 数据库，输入 RESTORE 继续：" CONFIRM
[[ "$CONFIRM" == "RESTORE" ]] || { echo "已取消。"; exit 1; }
docker compose stop api scheduler maintenance web || true
gzip -dc "$FILE" | docker compose exec -T mysql sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
docker compose run --rm migrate
docker compose up -d api scheduler maintenance web
echo "恢复完成。"
