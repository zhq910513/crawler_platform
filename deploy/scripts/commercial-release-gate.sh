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
release_env="$(bash deploy/scripts/resolve-release-version.sh --export 2>/dev/null || true)"
if [ -n "$release_env" ]; then
  eval "$release_env"
fi

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
run_step "前端字典重复键检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-frontend-dictionary-duplicates.py
run_step "前端可见文案检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-frontend-ui-copy.py
run_step "版本一致性检查" bash deploy/scripts/check-version-consistency.sh
run_step "MySQL 标识符长度检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-mysql-identifiers.py backend/app/models.py
run_step "MySQL JSON 默认值兼容检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-mysql-json-defaults.py
run_step "Alembic 迁移图检查（Docker 工具容器）" cp_python_tool deploy/scripts/check-alembic-graph.py

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
    log "前端镜像构建测试（Dockerfile 注入版本元信息）"
    cp_compose build web || fail "前端镜像构建未通过"
    log "前端 /version.json 镜像产物检查"
    image_tag="$(cp_env_value .env PLATFORM_IMAGE_TAG)"
    image_tag="${image_tag:-${RELEASE_VERSION:-latest}}"
    version_json="$(docker run --rm --entrypoint cat "crawler_platform_web:${image_tag}" /usr/share/nginx/html/version.json 2>/dev/null || true)"
    printf '%s\n' "$version_json"
    if ! printf '%s' "$version_json" | grep -Eq '"version"[[:space:]]*:[[:space:]]*"'"${RELEASE_VERSION:-}"'"'; then
      fail "前端 /version.json 未正确写入发布版本"
    fi
  else
    log "前端构建测试（非严格模式）"
    cp_compose build web || risk "前端镜像构建未通过，非严格模式记录为风险"
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
