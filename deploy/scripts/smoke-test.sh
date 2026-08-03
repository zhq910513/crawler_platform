#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker

# 默认使用 Docker 工具容器，避免客户宿主机 Python 版本过旧导致 smoke-test 误失败。
# 只有显式 CP_USE_HOST_TOOLS=1 且宿主机 Python 足够新时才走宿主机。
if [ "${CP_USE_HOST_TOOLS:-0}" = "1" ] && cp_host_python_modern python3; then
  exec python3 deploy/scripts/smoke-test.py "$@"
fi

cp_warn "使用临时 Python 3.12 工具容器执行 smoke-test；宿主机 Python/npm 不参与。"
exec docker run --rm \
  -v "$PWD":"$PWD" \
  -w "$PWD" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network host \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  "${SMOKE_PYTHON_TOOL_IMAGE:-python:3.12-alpine}" \
  sh -lc 'apk add --no-cache docker-cli curl >/dev/null 2>&1 || true; python deploy/scripts/smoke-test.py "$@"' smoke-test "$@"
