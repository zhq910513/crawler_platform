#!/usr/bin/env bash
# Shared host compatibility helpers for crawler_platform deployment scripts.
# Keep this file conservative: CentOS 7 Bash 4.x compatible, no jq/python/npm required on host.

cp_info() { printf '✅ %s\n' "$*"; }
cp_warn() { printf '⚠️  %s\n' "$*" >&2; }
cp_error() { printf '❌ %s\n' "$*" >&2; }
cp_die() { cp_error "$*"; return 1; }

cp_root_dir() {
  local src="${BASH_SOURCE[0]:-$0}"
  local dir
  dir="$(cd "$(dirname "$src")/../.." >/dev/null 2>&1 && pwd)" || return 1
  printf '%s\n' "$dir"
}

cp_command_exists() { command -v "$1" >/dev/null 2>&1; }

cp_detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    CP_COMPOSE_KIND="v2"
    return 0
  fi
  if cp_command_exists docker-compose && docker-compose version >/dev/null 2>&1; then
    CP_COMPOSE_KIND="v1"
    return 0
  fi
  CP_COMPOSE_KIND=""
  return 1
}

cp_compose() {
  if [ "${CP_COMPOSE_KIND:-}" = "v2" ] || docker compose version >/dev/null 2>&1; then
    CP_COMPOSE_KIND="v2"
    docker compose "$@"
    return $?
  fi
  if [ "${CP_COMPOSE_KIND:-}" = "v1" ] || { cp_command_exists docker-compose && docker-compose version >/dev/null 2>&1; }; then
    CP_COMPOSE_KIND="v1"
    docker-compose "$@"
    return $?
  fi
  cp_die "未检测到 docker compose v2 或 docker-compose。请先安装 Docker Compose。"
}

cp_require_docker() {
  cp_command_exists docker || cp_die "Docker 未安装。请先安装 Docker。" || return 1
  docker info >/dev/null 2>&1 || cp_die "Docker 服务不可用，或当前用户无 Docker 权限。请检查 systemctl status docker、docker group、/var/run/docker.sock。" || return 1
  cp_detect_compose || cp_die "Docker Compose 不可用。推荐安装 Docker Compose v2；旧 docker-compose v1 仅作为有限回退。" || return 1
}

cp_version_ge_20_10() {
  local v major minor
  v="$(docker version --format '{{.Server.Version}}' 2>/dev/null | sed 's/[^0-9.].*$//')"
  major="$(printf '%s' "$v" | awk -F. '{print $1+0}')"
  minor="$(printf '%s' "$v" | awk -F. '{print $2+0}')"
  if [ "$major" -gt 20 ]; then return 0; fi
  if [ "$major" -eq 20 ] && [ "$minor" -ge 10 ]; then return 0; fi
  return 1
}


cp_docker_server_version() {
  docker version --format '{{.Server.Version}}' 2>/dev/null | sed 's/[^0-9.].*$//' || true
}

cp_warn_min_docker() {
  if cp_version_ge_20_10; then
    cp_info "Docker 版本满足建议值 20.10+：$(cp_docker_server_version || echo unknown)"
    return 0
  fi
  cp_warn "Docker 版本低于建议值 20.10：$(cp_docker_server_version || echo unknown)。不会阻断部署；若后续构建/运行失败，请优先升级 Docker/Compose。"
  return 0
}

cp_require_min_docker() {
  if [ "${STRICT_DOCKER_VERSION:-0}" = "1" ]; then
    cp_version_ge_20_10 || cp_die "Docker 版本低于强制最低要求 20.10：$(cp_docker_server_version || echo unknown)。" || return 1
  else
    cp_warn_min_docker
  fi
}

cp_tool_python_image() { printf '%s\n' "${PYTHON_TOOL_IMAGE:-python:3.12-slim}"; }
cp_tool_node_image() { printf '%s\n' "${NODE_TOOL_IMAGE:-node:22-alpine}"; }
cp_tool_curl_image() { printf '%s\n' "${CURL_TOOL_IMAGE:-curlimages/curl:8.10.1}"; }

cp_host_python_modern() {
  local py="${1:-python3}"
  cp_command_exists "$py" || return 1
  "$py" - <<'PYCHECK' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PYCHECK
}

cp_python_tool() {
  # Run Python tooling in a container by default. Host Python is used only when explicitly enabled
  # and modern enough, so old customer hosts do not break deployment checks.
  if [ "${CP_USE_HOST_TOOLS:-0}" = "1" ] && cp_host_python_modern python3; then
    python3 "$@"
    return $?
  fi
  cp_require_docker || return 1
  docker run --rm -v "${ROOT_DIR:-$(pwd)}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend "$(cp_tool_python_image)" python "$@"
}

cp_python_tool_sh() {
  if [ "${CP_USE_HOST_TOOLS:-0}" = "1" ] && cp_host_python_modern python3; then
    sh -lc "$*"
    return $?
  fi
  cp_require_docker || return 1
  docker run --rm -v "${ROOT_DIR:-$(pwd)}:/workspace" -w /workspace -e PYTHONPATH=/workspace/backend "$(cp_tool_python_image)" sh -lc "$*"
}

cp_node_tool_sh() {
  cp_require_docker || return 1
  docker run --rm -v "${ROOT_DIR:-$(pwd)}:/workspace" -w /workspace/frontend -e NPM_CONFIG_REGISTRY="${NPM_REGISTRY:-https://registry.npmmirror.com}" "$(cp_tool_node_image)" sh -lc "$*"
}

cp_curl_tool() {
  if cp_command_exists curl; then
    curl "$@"
    return $?
  fi
  cp_require_docker || return 1
  docker run --rm --network host -v "${ROOT_DIR:-$(pwd)}:${ROOT_DIR:-$(pwd)}" -w "${ROOT_DIR:-$(pwd)}" "$(cp_tool_curl_image)" "$@"
}

cp_env_value() {
  local file="$1" key="$2"
  awk -F= -v k="$key" '$1==k {sub(/^[^=]*=/,"",$0); gsub(/^\"|\"$/,"",$0); gsub(/^'"'"'|'"'"'$/,"",$0); print $0}' "$file" 2>/dev/null | tail -n 1
}

cp_host_arch() { uname -m 2>/dev/null || echo unknown; }

cp_os_release_line() {
  if [ -r /etc/os-release ]; then
    . /etc/os-release
    printf '%s\n' "${PRETTY_NAME:-${ID:-unknown}}"
  else
    printf 'unknown\n'
  fi
}

cp_has_sudo() {
  if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then return 0; fi
  cp_command_exists sudo && sudo -n true >/dev/null 2>&1
}

cp_sudo() {
  if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then "$@"; return $?; fi
  if cp_command_exists sudo; then sudo "$@"; return $?; fi
  cp_die "当前用户不是 root 且 sudo 不可用：$*"
}

cp_check_crlf() {
  local target="${1:-.}"
  if cp_command_exists grep; then
    if grep -RIl $'\r' "$target" --include='*.sh' --include='*.py' --include='*.yml' --include='*.yaml' --include='*.env' >/tmp/crawler_platform_crlf.$$ 2>/dev/null; then
      if [ -s /tmp/crawler_platform_crlf.$$ ]; then
        cp_warn "检测到 CRLF 文件，Linux 下可能出现 bad interpreter："
        cat /tmp/crawler_platform_crlf.$$ >&2
        rm -f /tmp/crawler_platform_crlf.$$
        return 1
      fi
    fi
    rm -f /tmp/crawler_platform_crlf.$$
  fi
  return 0
}

cp_fix_project_permissions() {
  find deploy agent cicd -type f \( -name '*.sh' -o -name '*.py' \) -exec sed -i 's/\r$//' {} \; 2>/dev/null || true
  chmod +x deploy/scripts/*.sh 2>/dev/null || true
  chmod +x agent/install-linux.sh 2>/dev/null || true
}

cp_has_docker_mirror() {
  [ -r /etc/docker/daemon.json ] && grep -q 'registry-mirrors' /etc/docker/daemon.json
}

cp_warn_cn_mirrors() {
  if ! cp_has_docker_mirror; then
    cp_warn "未检测到 Docker registry-mirrors。国内服务器可能拉取镜像极慢或失败；可执行：./deploy/scripts/prepare-cn-mirrors.sh --yes"
  fi
}

cp_wait_http() {
  local url="$1" timeout="${2:-120}" step="${3:-2}" start now
  start="$(date +%s)"
  while :; do
    if cp_command_exists curl; then
      curl -fsS "$url" >/dev/null 2>&1 && return 0
    else
      docker run --rm --network host curlimages/curl:8.10.1 -fsS "$url" >/dev/null 2>&1 && return 0
    fi
    now="$(date +%s)"
    if [ $((now-start)) -ge "$timeout" ]; then return 1; fi
    sleep "$step"
  done
}

cp_print_diagnostics() {
  echo "---- crawler_platform diagnostics ----" >&2
  echo "time: $(date '+%F %T %z' 2>/dev/null || true)" >&2
  echo "os: $(cp_os_release_line)" >&2
  echo "arch: $(cp_host_arch)" >&2
  echo "pwd: $(pwd)" >&2
  echo "disk:" >&2; df -h . /data 2>/dev/null >&2 || df -h . >&2 || true
  echo "memory:" >&2; free -m 2>/dev/null >&2 || true
  echo "docker version:" >&2; docker version 2>/dev/null >&2 || true
  echo "docker compose ps:" >&2; cp_compose ps 2>/dev/null >&2 || true
  echo "api logs:" >&2; cp_compose logs --tail=120 api 2>/dev/null >&2 || true
  echo "scheduler logs:" >&2; cp_compose logs --tail=120 scheduler 2>/dev/null >&2 || true
  echo "mysql logs:" >&2; cp_compose logs --tail=80 mysql 2>/dev/null >&2 || true
  echo "agent smoke logs:" >&2; docker logs --tail=120 crawler-agent-smoke 2>/dev/null >&2 || true
  echo "docker system df:" >&2; docker system df 2>/dev/null >&2 || true
  echo "---- end diagnostics ----" >&2
}

cp_trap_diagnostics() {
  trap 'rc=$?; if [ "$rc" -ne 0 ]; then cp_error "脚本失败，退出码：$rc"; cp_print_diagnostics; fi; exit "$rc"' EXIT
}
