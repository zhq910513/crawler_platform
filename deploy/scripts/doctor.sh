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

check_required_cmd(){ if cp_command_exists "$1"; then ok "最低依赖存在：$1"; else fail "缺少最低依赖：$1"; fi; }
check_optional_cmd(){ if cp_command_exists "$1"; then ok "宿主机可选工具存在：$1"; else warn "宿主机可选工具缺失：$1；部署流程会尽量使用 Docker 工具容器替代。"; fi; }

ok "项目目录：$ROOT_DIR"
ok "系统：$(cp_os_release_line)"
ok "架构：$(cp_host_arch)"

if [ -n "${BASH_VERSION:-}" ]; then ok "Bash：${BASH_VERSION}"; else fail "当前 shell 不是 bash，部署脚本需要 bash。"; fi
if [ -f .env ]; then ok ".env 存在"; else warn ".env 不存在，Fresh Install 会从 .env.example 生成；首次生成后需要填写/生成强密码。"; fi

# 只有这些属于最低部署条件。Python/npm/curl/git/jq 等不能作为阻断项。
check_required_cmd docker
if cp_command_exists docker; then
  if docker info >/dev/null 2>&1; then ok "Docker daemon 可用，当前用户具备 Docker 权限"; else fail "Docker daemon 不可用或当前用户无 Docker 权限。"; fi
  if cp_detect_compose; then ok "Docker Compose 可用：$CP_COMPOSE_KIND"; else fail "Docker Compose 不可用。"; fi
  cp_warn_min_docker || true
  if cp_has_docker_mirror; then ok "已检测到 Docker registry-mirrors"; else warn "未检测到 Docker registry-mirrors，国内网络可能拉取镜像失败。"; fi
else
  fail "Docker 未安装。"
fi

check_optional_cmd curl
check_optional_cmd sed
check_optional_cmd awk
check_optional_cmd grep
check_optional_cmd git
check_optional_cmd python3
check_optional_cmd npm
check_optional_cmd openssl

if cp_command_exists python3; then
  if cp_host_python_modern python3; then ok "宿主机 Python 足够新，可作为可选工具使用"; else warn "宿主机 Python 版本较旧；不会阻断部署，Python 检查/测试将使用 Docker 工具容器。"; fi
fi
if cp_command_exists npm; then
  warn "检测到宿主机 npm；正式构建仍优先使用 Node Docker 工具容器，避免宿主机 Node 版本污染。"
fi

if cp_check_crlf deploy >/dev/null 2>&1; then ok "脚本换行符检查通过"; else warn "存在 CRLF 文件，prepare/deploy 会尝试自动修复；若仍失败请执行 sed 去除 CRLF。"; fi

for f in deploy/scripts/test-server-validate.sh deploy/scripts/reset-test-server.sh deploy/scripts/smoke-test.sh deploy/scripts/prepare-cn-mirrors.sh deploy/scripts/commercial-release-gate.sh; do
  if [ -x "$f" ]; then ok "脚本可执行：$f"; else warn "脚本未设置可执行权限：$f；prepare 会尝试自动 chmod。"; fi
done

avail_kb="$(df -Pk . | awk 'NR==2 {print $4+0}')"
if [ "$avail_kb" -ge 10485760 ]; then ok "当前目录剩余磁盘 >= 10GB"; else warn "当前目录剩余磁盘不足 10GB；不阻断预检，但构建镜像或日志增长可能失败。"; fi
inode_pct="$(df -Pi . | awk 'NR==2 {gsub(/%/,"",$5); print $5+0}')"
if [ "$inode_pct" -lt 90 ]; then ok "inode 使用率 < 90%"; else warn "inode 使用率过高：${inode_pct}%；不阻断预检，但后续写文件可能失败。"; fi

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
  timedatectl 2>/dev/null | sed 's/^/  /' || warn "timedatectl 存在但无法读取时间同步状态。"
else
  warn "未检测到 timedatectl，无法自动确认 NTP；不阻断部署。"
fi

echo "---- 体检结果：failures=$failures warnings=$warnings ----"
if [ "$failures" -gt 0 ]; then
  echo "❌ 最低部署条件不满足，禁止继续自动部署。" >&2
  exit 1
fi
echo "✅ 最低部署条件满足；warnings 仅提示风险，不会打断部署流程。"
exit 0
