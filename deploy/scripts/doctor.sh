#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

failures=0
warnings=0
ok(){ cp_info "$*"; }
warn(){ warnings=$((warnings+1)); cp_warn "$*"; }
fail(){ failures=$((failures+1)); cp_error "$*"; }

check_cmd(){ if cp_command_exists "$1"; then ok "命令存在：$1"; else warn "命令缺失：$1；脚本会尽量用工具容器替代。"; fi; }

ok "项目目录：$ROOT_DIR"
ok "系统：$(cp_os_release_line)"
ok "架构：$(cp_host_arch)"

if [ -f .env ]; then ok ".env 存在"; else warn ".env 不存在，Fresh Install 会从 .env.example 生成。"; fi

check_cmd bash
check_cmd docker
check_cmd curl
check_cmd sed
check_cmd awk
check_cmd grep
check_cmd python3
check_cmd npm

if cp_command_exists docker; then
  if docker info >/dev/null 2>&1; then ok "Docker daemon 可用"; else fail "Docker daemon 不可用或无权限。"; fi
  if cp_detect_compose; then ok "Docker Compose 可用：$CP_COMPOSE_KIND"; else fail "Docker Compose 不可用。"; fi
  if cp_version_ge_20_10; then ok "Docker 版本满足 20.10+：$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"; else fail "Docker 版本低于 20.10：$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"; fi
  if cp_has_docker_mirror; then ok "已检测到 Docker registry-mirrors"; else warn "未检测到 Docker registry-mirrors，国内网络可能拉取镜像失败。"; fi
else
  fail "Docker 未安装。"
fi

if cp_check_crlf deploy >/dev/null 2>&1; then ok "脚本换行符检查通过"; else warn "存在 CRLF 文件，请执行：find deploy agent cicd -type f \( -name '*.sh' -o -name '*.py' \) -exec sed -i 's/\\r$//' {} \;"; fi

for f in deploy/scripts/test-server-validate.sh deploy/scripts/reset-test-server.sh deploy/scripts/smoke-test.sh deploy/scripts/prepare-cn-mirrors.sh; do
  if [ -x "$f" ]; then ok "脚本可执行：$f"; else warn "脚本未设置可执行权限：$f"; fi
done

# Disk and inode checks.
avail_kb="$(df -Pk . | awk 'NR==2 {print $4+0}')"
if [ "$avail_kb" -ge 10485760 ]; then ok "当前目录剩余磁盘 >= 10GB"; else warn "当前目录剩余磁盘不足 10GB。"; fi
inode_pct="$(df -Pi . | awk 'NR==2 {gsub(/%/,"",$5); print $5+0}')"
if [ "$inode_pct" -lt 90 ]; then ok "inode 使用率 < 90%"; else warn "inode 使用率过高：${inode_pct}%"; fi

# Ports.
ports="${WEB_PORT:-8080} 3306 6379 5000"
for p in $ports; do
  if command -v ss >/dev/null 2>&1; then
    if ss -lnt 2>/dev/null | awk '{print $4}' | grep -q ":$p$"; then warn "端口 $p 已被监听；若非当前平台容器，可能冲突。"; else ok "端口 $p 当前未被宿主直接占用"; fi
  elif command -v netstat >/dev/null 2>&1; then
    if netstat -lnt 2>/dev/null | awk '{print $4}' | grep -q ":$p$"; then warn "端口 $p 已被监听；若非当前平台容器，可能冲突。"; else ok "端口 $p 当前未被宿主直接占用"; fi
  else
    warn "无 ss/netstat，跳过端口 $p 检查。"
  fi
done

if command -v getenforce >/dev/null 2>&1; then
  se="$(getenforce 2>/dev/null || true)"
  if [ "$se" = "Enforcing" ]; then warn "SELinux 为 Enforcing，Docker 目录挂载可能受限。"; else ok "SELinux：${se:-unknown}"; fi
else
  ok "未检测到 SELinux 工具。"
fi

if command -v timedatectl >/dev/null 2>&1; then
  timedatectl 2>/dev/null | sed 's/^/  /' || true
else
  warn "未检测到 timedatectl，无法自动确认 NTP。"
fi

echo "---- 体检结果：failures=$failures warnings=$warnings ----"
if [ "$failures" -gt 0 ]; then exit 1; fi
exit 0
