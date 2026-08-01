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

cp_require_min_docker() {
  cp_version_ge_20_10 || cp_die "Docker 版本过低。最低建议 Docker 20.10+，当前：$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)。" || return 1
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
  chmod +x deploy/templates/project/bootstrap.sh 2>/dev/null || true
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
