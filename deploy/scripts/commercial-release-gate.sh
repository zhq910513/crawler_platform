#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
STRICT_FRONTEND_BUILD="${STRICT_FRONTEND_BUILD:-1}"
RUN_BACKEND_TESTS="${RUN_BACKEND_TESTS:-1}"
FAILED=0
RISK=0

log() { printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; }
risk() { printf 'RISK: %s\n' "$*" >&2; RISK=1; }
run_step() { local name="$1"; shift; log "$name"; "$@" || fail "$name 未通过"; }

cd "$ROOT_DIR" || exit 1

# 商业发布门禁必须只依赖最低宿主机能力：Docker + Compose + bash。
# Python/npm 等检查全部通过工具容器执行，避免客户旧宿主机 Python 3.6/2.7、无 npm、无 node_modules 时误失败。
if ! cp_require_docker; then
  fail "最低部署条件不满足：Docker/Docker Compose 不可用"
else
  cp_warn_min_docker || true
fi

if [ -d .git ]; then
  run_step "git diff --check" git diff --check
else
  risk "当前目录不是 git 工作树，跳过 git diff --check"
fi

log "Python 编译检查（Docker 工具容器）"
cp_python_tool_sh "python -m compileall backend/app backend/tests backend/migrations agent/crawler_agent runtime >/tmp/crawler_platform_compile.log" || fail "Python 编译检查未通过；查看工具容器输出或 /tmp/crawler_platform_compile.log"

run_step "商业契约扫描（Docker 工具容器）" cp_python_tool deploy/scripts/commercial-contract-scan.py
run_step "宿主机兼容扫描（Docker 工具容器）" cp_python_tool deploy/scripts/host-compat-scan.py
run_step "MySQL 标识符长度检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-mysql-identifiers.py backend/app/models.py

log "Shell bash -n 检查"
while IFS= read -r -d '' file; do
  bash -n "$file" || FAILED=1
done < <(find . -path './frontend/node_modules' -prune -o -type f -name '*.sh' -print0)

if [ "$RUN_BACKEND_TESTS" = "1" ]; then
  log "后端契约/回归测试（Docker 工具容器）"
  cp_python_tool_sh "pip install --no-cache-dir -i ${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple} -r backend/requirements-test.txt >/tmp/crawler_platform_test_pip.log && cd backend && python -m pytest -q" || fail "后端测试未通过"
else
  risk "RUN_BACKEND_TESTS=0，已跳过后端测试"
fi

if [ -f frontend/package.json ]; then
  if [ "$STRICT_FRONTEND_BUILD" = "1" ]; then
    log "前端构建测试（Node Docker 工具容器）"
    cp_node_tool_sh "npm ci --no-audit --no-fund && npm run build" || fail "前端构建未通过"
  else
    log "前端构建测试（非严格模式）"
    cp_node_tool_sh "npm ci --no-audit --no-fund && npm run build" || risk "前端构建未通过，非严格模式记录为风险"
  fi
fi

if [ "$FAILED" -eq 1 ]; then
  printf '\nRELEASE_GATE=FAIL\n'
  exit 1
fi
if [ "$RISK" -eq 1 ]; then
  printf '\nRELEASE_GATE=PASS_WITH_RISK\n'
  exit 0
fi
printf '\nRELEASE_GATE=PASS\n'
