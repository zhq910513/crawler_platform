#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker
cp_warn_min_docker || true
cp_info "使用 Python Docker 工具容器执行编译检查，避免宿主机 Python 旧版本误判。"
cp_python_tool_sh "python -m compileall backend/app backend/tests backend/migrations agent/crawler_agent runtime"
cp_info "容器化 Python 编译检查通过。"
