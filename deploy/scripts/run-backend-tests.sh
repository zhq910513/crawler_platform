#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
cp_info "使用 Python Docker 工具容器执行后端测试，避免宿主机 Python/pip 版本影响。"
cp_python_tool_sh "pip install --no-cache-dir -i $PIP_INDEX_URL -r backend/requirements-test.txt >/tmp/test-pip.log && python -m pytest backend/tests/test_rebuild_contract.py -q"
