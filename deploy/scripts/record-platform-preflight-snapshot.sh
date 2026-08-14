#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker
source_arg="${1:-DEPLOY}"
cp_info "保存平台自检快照：source=${source_arg}"
if ! cp_compose exec -T api python -m app.preflight_cli --source "$source_arg"; then
  cp_warn "平台自检快照保存失败；不影响平台主服务，但运行总览可能缺少部署后自动检测记录。"
  exit 1
fi
