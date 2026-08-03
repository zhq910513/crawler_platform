#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STRICT_FRONTEND_BUILD="${STRICT_FRONTEND_BUILD:-1}"
FAILED=0
RISK=0

log() { printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
fail() { printf 'FAIL: %s\n' "$*" >&2; FAILED=1; }
risk() { printf 'RISK: %s\n' "$*" >&2; RISK=1; }
run_step() { local name="$1"; shift; log "$name"; "$@" || fail "$name 未通过"; }

cd "$ROOT_DIR" || exit 1

if [ -d .git ]; then
  run_step "git diff --check" git diff --check
else
  risk "当前目录不是 git 工作树，跳过 git diff --check"
fi

if command -v python >/dev/null 2>&1; then
  log "Python 编译检查"
  python -m compileall backend/app backend/tests backend/migrations agent/crawler_agent runtime >/tmp/crawler_platform_compile.log || fail "Python 编译检查未通过"
  run_step "商业契约扫描" python deploy/scripts/commercial-contract-scan.py
  run_step "MySQL 标识符长度检查" python deploy/scripts/check-mysql-identifiers.py backend/app/models.py
else
  fail "未找到 python，无法执行后端编译和商业契约扫描"
fi

log "Shell bash -n 检查"
while IFS= read -r -d '' file; do
  bash -n "$file" || FAILED=1
done < <(find . -path './frontend/node_modules' -prune -o -type f -name '*.sh' -print0)

if command -v python >/dev/null 2>&1; then
  log "后端契约/回归测试"
  (cd backend && python -m pytest -q) || fail "后端测试未通过"
fi

if [ -f frontend/package.json ]; then
  if command -v npm >/dev/null 2>&1 && [ -d frontend/node_modules ]; then
    log "前端构建测试"
    (cd frontend && npm run build) || fail "前端构建未通过"
  elif [ "$STRICT_FRONTEND_BUILD" = "1" ]; then
    fail "缺少 npm 或 frontend/node_modules，正式发布门禁要求完成前端构建"
  else
    risk "缺少 npm 或 frontend/node_modules，已按非严格模式跳过前端构建"
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
