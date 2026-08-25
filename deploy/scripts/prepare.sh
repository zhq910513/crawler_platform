#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_fix_project_permissions
mkdir -p data/mysql data/redis data/task-logs data/backups
chmod 0750 data data/task-logs 2>/dev/null || true
chmod 0700 data/mysql data/redis data/backups 2>/dev/null || true
chown -R 1000:1000 data/task-logs 2>/dev/null || true
if [ ! -f .env ]; then
  install -m 0600 .env.example .env 2>/dev/null || cp .env.example .env
  chmod 0600 .env 2>/dev/null || true
  echo "已生成 .env，请先修改全部 ReplaceWith... 配置后重新执行，或测试服使用 bash deploy/scripts/reset-test-server.sh --yes 自动生成强密码。"
  exit 2
fi
chmod 0600 .env 2>/dev/null || true
bash deploy/scripts/configure-project-build-center.sh .env
bash deploy/scripts/check-env.sh .env
