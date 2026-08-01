#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker

# Prefer host Python 3.6+ to avoid downloading tool images on old customer hosts that already have python3.
if command -v python3 >/dev/null 2>&1 && python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 6) else 1)
PY
then
  exec python3 deploy/scripts/smoke-test.py "$@"
fi

cp_warn "宿主机无可用 Python 3.6+，改用临时 Python 3.12 工具容器执行 smoke-test。"
exec docker run --rm \
  -v "$PWD":"$PWD" \
  -w "$PWD" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network host \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  python:3.12-alpine \
  sh -lc 'apk add --no-cache docker-cli curl >/dev/null && python deploy/scripts/smoke-test.py "$@"' smoke-test "$@"
