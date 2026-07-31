#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
mkdir -p data/mysql data/redis data/task-logs data/backups
chmod 0750 data data/task-logs
chmod 0700 data/mysql data/redis data/backups
# backend container runs as uid/gid 1000.
chown -R 1000:1000 data/task-logs
if [[ ! -f .env ]]; then
  install -m 0600 .env.example .env
  echo "已生成 .env，请先修改全部 ReplaceWith... 配置后重新执行。"
  exit 2
fi
chmod 0600 .env
python3 deploy/scripts/validate-env.py .env
