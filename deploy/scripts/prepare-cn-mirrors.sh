#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"

YES=0
APPLY_SYSTEM=1
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --check-only) APPLY_SYSTEM=0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

DOCKER_MIRRORS="${DOCKER_REGISTRY_MIRRORS:-https://docker.m.daocloud.io,https://mirror.ccs.tencentyun.com}"
NPM_REGISTRY_VALUE="${NPM_REGISTRY:-https://registry.npmmirror.com}"
PIP_INDEX_VALUE="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
APT_MIRROR_VALUE="${APT_MIRROR:-mirrors.tuna.tsinghua.edu.cn}"
APK_MIRROR_VALUE="${APK_MIRROR:-mirrors.aliyun.com}"

if [ "$YES" != "1" ] && [ "$APPLY_SYSTEM" = "1" ]; then
  cat <<MSG
该脚本会检查并可选写入国内镜像源配置：
- Docker /etc/docker/daemon.json registry-mirrors
- 项目 frontend/.npmrc registry
- 用户 pip.conf index-url
- .env 镜像源变量
系统级 Docker 配置需要 root/sudo，并可能重启 Docker。确认执行请追加：--yes
MSG
  exit 2
fi

cd "$ROOT_DIR"

cp_info "当前系统：$(cp_os_release_line)"
cp_info "Docker 镜像源：$DOCKER_MIRRORS"
cp_info "npm 镜像源：$NPM_REGISTRY_VALUE"
cp_info "pip 镜像源：$PIP_INDEX_VALUE"
cp_info "apt 镜像域名：$APT_MIRROR_VALUE"
cp_info "apk 镜像域名：$APK_MIRROR_VALUE"

if [ ! -f .env ]; then
  cp .env.example .env
  chmod 0600 .env || true
fi

# Ensure .env has mirror variables; replace existing values conservatively.
ensure_env_key() {
  key="$1"; value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s#^${key}=.*#${key}=${value}#" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}
ensure_env_key DOCKER_REGISTRY_MIRRORS "$DOCKER_MIRRORS"
ensure_env_key NPM_REGISTRY "$NPM_REGISTRY_VALUE"
ensure_env_key PIP_INDEX_URL "$PIP_INDEX_VALUE"
ensure_env_key APT_MIRROR "$APT_MIRROR_VALUE"
ensure_env_key APK_MIRROR "$APK_MIRROR_VALUE"

# Project npm config is safe and repo-local.
printf 'registry=%s\nfund=false\naudit=false\n' "$NPM_REGISTRY_VALUE" > frontend/.npmrc

# User pip config is non-root safe.
mkdir -p "${HOME:-/root}/.pip"
cat > "${HOME:-/root}/.pip/pip.conf" <<PIPCONF
[global]
index-url = ${PIP_INDEX_VALUE}
timeout = 120
trusted-host = $(printf '%s' "$PIP_INDEX_VALUE" | awk -F/ '{print $3}')
PIPCONF

if [ "$APPLY_SYSTEM" = "1" ]; then
  if cp_has_sudo; then
    tmp="$(mktemp)"
    json_mirrors="$(printf '%s' "$DOCKER_MIRRORS" | awk -F, '{sep=""; for(i=1;i<=NF;i++){gsub(/^[ \t]+|[ \t]+$/,"",$i); if($i!=""){printf "%s\"%s\"", sep, $i; sep=","}}}')"
    cat > "$tmp" <<JSON
{
  "registry-mirrors": [${json_mirrors}],
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
JSON
    cp_sudo mkdir -p /etc/docker
    if [ -f /etc/docker/daemon.json ]; then cp_sudo cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak.$(date +%Y%m%d%H%M%S)"; fi
    cp_sudo sh -c "cat > /etc/docker/daemon.json" < "$tmp"
    rm -f "$tmp"
    cp_info "已写入 /etc/docker/daemon.json。"
    if cp_command_exists systemctl; then
      cp_warn "需要重启 Docker 才能生效。脚本将执行 systemctl restart docker。"
      cp_sudo systemctl restart docker
    else
      cp_warn "未检测到 systemctl，请手动重启 Docker 服务。"
    fi
  else
    cp_warn "当前用户无 root/sudo 权限，已跳过 /etc/docker/daemon.json 写入。"
  fi
fi

cp_info "国内镜像源配置完成。"
