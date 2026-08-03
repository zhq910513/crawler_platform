#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
PYTHON_IMAGE="${PYTHON_IMAGE:-python:3.12-slim}"
PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
docker run --rm -v "$ROOT_DIR:/app" -w /app -e PYTHONPATH=/app/backend "$PYTHON_IMAGE" sh -lc "pip install --no-cache-dir -i $PIP_INDEX_URL -r backend/requirements-test.txt >/tmp/test-pip.log && python -m pytest backend/tests/test_rebuild_contract.py -q"
