#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics

YES=0
BUILD=1
PULL=1
AUTO_MIRRORS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --no-build) BUILD=0 ;;
    --no-pull) PULL=0 ;;
    --prepare-cn-mirrors) AUTO_MIRRORS=1 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$YES" != "1" ]; then
  echo "该脚本会清空测试服数据：./data/mysql、./data/redis、./data/task-logs、./data/backups、/data/crawler-platform/projects、/var/lib/crawler-agent。"
  echo "确认零数据重置请追加参数：--yes"
  exit 2
fi

cp_fix_project_permissions
cp_require_docker
cp_require_min_docker
cp_warn_cn_mirrors
if [ "$AUTO_MIRRORS" = "1" ]; then
  ./deploy/scripts/prepare-cn-mirrors.sh --yes || cp_warn "国内镜像源自动配置未完成，请检查权限。"
fi

run_py() {
  if command -v python3 >/dev/null 2>&1 && python3 - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 6) else 1)
PY
  then
    python3 "$@"
  else
    docker run --rm -v "$ROOT_DIR":"$ROOT_DIR" -w "$ROOT_DIR" python:3.12-alpine python "$@"
  fi
}

random_secret() {
  if command -v openssl >/dev/null 2>&1; then openssl rand -base64 36 | tr -d '=+/\n' | cut -c1-36; return 0; fi
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n' | cut -c1-36; echo
}
if [ ! -f .env ]; then
  cp .env.example .env
fi
if grep -qE 'ReplaceWith|change-this|Admin@123456' .env; then
  r1="$(random_secret)"; r2="$(random_secret)"; r3="$(random_secret)"; r4="$(random_secret)$(random_secret)"; r5="$(random_secret)$(random_secret)"; r6="Admin@$(random_secret)"
  sed -i \
    -e "s#ReplaceWithStrongRootPassword#${r1}#g" \
    -e "s#ReplaceWithStrongDatabasePassword#${r2}#g" \
    -e "s#ReplaceWithStrongRedisPassword#${r3}#g" \
    -e "s#ReplaceWithAtLeast32CharactersJwtSecret#${r4}#g" \
    -e "s#ReplaceWithLongEncryptionMasterKey#${r5}#g" \
    -e "s#ReplaceWithStrongAdminPassword#${r6}#g" \
    -e "s#Admin@123456#${r6}#g" .env
  echo '已从 .env.example 生成/修正测试服 .env，并自动替换强密码占位符。'
fi
chmod 0600 .env || true

./deploy/scripts/check-env.sh .env
run_py deploy/scripts/check-mysql-identifiers.py

WEB_PORT_VALUE="$(cp_env_value .env WEB_PORT)"; WEB_PORT_VALUE="${WEB_PORT_VALUE:-8080}"

echo "停止并清理测试服容器..."
cp_compose down --remove-orphans || true
docker rm -f crawler-agent crawler-agent-smoke >/dev/null 2>&1 || true

echo "清理测试服数据目录..."
rm -rf ./data/mysql ./data/redis ./data/task-logs ./data/backups ./data/smoke
mkdir -p ./data/mysql ./data/redis ./data/task-logs ./data/backups ./data/smoke
if cp_has_sudo; then
  cp_sudo rm -rf /data/crawler-platform/projects /var/lib/crawler-agent 2>/dev/null || true
  cp_sudo mkdir -p /data/crawler-platform/projects /var/lib/crawler-agent/runs
  cp_sudo chmod -R 0775 /data/crawler-platform /var/lib/crawler-agent 2>/dev/null || true
else
  mkdir -p /data/crawler-platform/projects /var/lib/crawler-agent/runs 2>/dev/null || cp_warn "无法创建 /data/crawler-platform 或 /var/lib/crawler-agent，请使用 root/sudo 或调整目录权限。"
fi

if [ "$BUILD" = "1" ]; then
  if [ "$PULL" = "1" ]; then
    cp_compose build --pull
  else
    cp_compose build
  fi
fi

echo "启动 MySQL / Redis 并执行空库初始化..."
cp_compose up -d mysql redis
cp_compose run --rm migrate

echo "启动平台服务..."
cp_compose up -d api scheduler maintenance web

echo "等待 API 健康检查..."
if cp_wait_http "http://127.0.0.1:${WEB_PORT_VALUE}/health" 120 2; then
  echo "✅ API 健康检查通过：http://127.0.0.1:${WEB_PORT_VALUE}/health"
  echo "登录账号：$(cp_env_value .env ADMIN_USERNAME || echo admin)"
  echo "登录密码请查看 .env 中 ADMIN_PASSWORD。"
  exit 0
fi

echo "API 健康检查超时，请查看日志：docker compose logs --tail=300 api" >&2
exit 1
