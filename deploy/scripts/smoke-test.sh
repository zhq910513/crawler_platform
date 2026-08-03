#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_require_docker

SMOKE_TOOL_TIMEOUT_SECONDS="${SMOKE_TOOL_TIMEOUT_SECONDS:-900}"
SMOKE_TOOL_CONTAINER="${SMOKE_TOOL_CONTAINER:-crawler-platform-smoke-tool-$$}"
SMOKE_PYTHON_TOOL_IMAGE="${SMOKE_PYTHON_TOOL_IMAGE:-python:3.12-alpine}"

cleanup_smoke_tool() {
  docker rm -f "$SMOKE_TOOL_CONTAINER" >/dev/null 2>&1 || true
}

on_interrupt() {
  cp_warn "收到中断信号，正在清理 smoke-test 工具容器：${SMOKE_TOOL_CONTAINER}"
  cleanup_smoke_tool
  exit 130
}
trap on_interrupt INT TERM

# smoke-test.py 只依赖 Python 标准库和宿主 Docker CLI。CentOS 7 常见 Python 3.6 也可运行，
# 因此优先使用宿主 python3，避免为了执行 smoke-test 再拉取/安装工具容器导致卡死。
if [ "${CP_SMOKE_FORCE_TOOL_CONTAINER:-0}" != "1" ] && cp_command_exists python3; then
  if python3 - <<'PYCHECK' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 6) else 1)
PYCHECK
  then
    cp_info "使用宿主 python3 执行 smoke-test；该脚本仅依赖标准库和 Docker CLI。"
    python3 deploy/scripts/smoke-test.py "$@"
    exit $?
  fi
fi

cp_warn "宿主 python3 不可用或低于 3.6，改用受控 Python 工具容器执行 smoke-test。"
cp_info "工具容器名称：${SMOKE_TOOL_CONTAINER}；超时：${SMOKE_TOOL_TIMEOUT_SECONDS}s；镜像：${SMOKE_PYTHON_TOOL_IMAGE}"
cleanup_smoke_tool

# 先显式拉取镜像，避免 docker run 阶段静默等待。这里不隐藏日志，便于定位国内网络/镜像源问题。
cp_info "准备 Python 工具镜像：${SMOKE_PYTHON_TOOL_IMAGE}"
docker image inspect "$SMOKE_PYTHON_TOOL_IMAGE" >/dev/null 2>&1 || docker pull "$SMOKE_PYTHON_TOOL_IMAGE"

container_id="$(docker run -d \
  --name "$SMOKE_TOOL_CONTAINER" \
  -v "$PWD":"$PWD" \
  -w "$PWD" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  --network host \
  -e DOCKER_HOST=unix:///var/run/docker.sock \
  -e SMOKE_COMMAND_TIMEOUT_SECONDS="${SMOKE_COMMAND_TIMEOUT_SECONDS:-600}" \
  "$SMOKE_PYTHON_TOOL_IMAGE" \
  sh -lc 'set -eu; echo "[smoke-tool] python=$(python --version 2>&1)"; if ! command -v docker >/dev/null 2>&1; then echo "[smoke-tool] installing docker-cli..."; if command -v apk >/dev/null 2>&1; then apk add --no-cache docker-cli; elif command -v apt-get >/dev/null 2>&1; then apt-get update && apt-get install -y --no-install-recommends docker.io && rm -rf /var/lib/apt/lists/*; else echo "no supported package manager for docker cli" >&2; exit 1; fi; fi; docker version; python deploy/scripts/smoke-test.py "$@"' \
  smoke-test "$@")"
cp_info "smoke-test 工具容器已启动：${container_id}"

docker logs -f "$SMOKE_TOOL_CONTAINER" &
logs_pid=$!
start_ts="$(date +%s)"
exit_code=""
while :; do
  running="$(docker inspect -f '{{.State.Running}}' "$SMOKE_TOOL_CONTAINER" 2>/dev/null || echo false)"
  if [ "$running" != "true" ]; then
    exit_code="$(docker inspect -f '{{.State.ExitCode}}' "$SMOKE_TOOL_CONTAINER" 2>/dev/null || echo 125)"
    break
  fi
  now_ts="$(date +%s)"
  if [ $((now_ts - start_ts)) -ge "$SMOKE_TOOL_TIMEOUT_SECONDS" ]; then
    cp_error "smoke-test 工具容器执行超过 ${SMOKE_TOOL_TIMEOUT_SECONDS}s，强制终止。"
    docker logs --tail=200 "$SMOKE_TOOL_CONTAINER" >&2 || true
    cleanup_smoke_tool
    kill "$logs_pid" >/dev/null 2>&1 || true
    exit 124
  fi
  sleep 2
done
wait "$logs_pid" >/dev/null 2>&1 || true
cleanup_smoke_tool
if [ "${exit_code:-125}" != "0" ]; then
  cp_error "smoke-test 失败，退出码：${exit_code:-125}"
  exit "${exit_code:-125}"
fi
cp_info "smoke-test 脚本执行完成。"
