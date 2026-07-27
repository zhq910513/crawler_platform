#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."
mkdir -p data/mysql data/redis data/task-logs data/backups
chown -R 1000:1000 data/task-logs
chmod 700 data/mysql data/redis data/backups
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "已生成 .env，请先修改所有 ReplaceWith... 配置。"
fi
