#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker
cp_fix_project_permissions || true
bash deploy/scripts/sync-runtime-version.sh
bash deploy/scripts/cleanup-obsolete-migrations.sh >/tmp/crawler_platform_migration_cleanup.log
cp_python_tool deploy/scripts/check-alembic-graph.py
cp_info "重建 migrate 镜像，确保容器内迁移文件与当前 Git 代码一致。"
cp_compose build migrate
cp_info "执行数据库迁移。"
cp_compose run --rm migrate
cp_info "当前 Alembic 版本："
cp_compose run --rm migrate alembic current
