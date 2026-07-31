#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

YES=0
BUILD=1
PULL=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --no-build) BUILD=0 ;;
    --no-pull) PULL=0 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [[ "$YES" != "1" ]]; then
  echo "该脚本会清空测试服数据：./data/mysql、./data/redis、./data/task-logs、./data/backups、/data/crawler-platform/projects、/var/lib/crawler-agent。"
  echo "确认零数据重置请追加参数：--yes"
  exit 2
fi

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "缺少命令：$1" >&2; exit 1; }
}
need_cmd docker
need_cmd python3
if ! docker compose version >/dev/null 2>&1; then
  echo "当前 Docker 不支持 'docker compose'，请安装 Docker Compose v2。" >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
text = p.read_text(encoding='utf-8')
repls = {
    'ReplaceWithStrongRootPassword': secrets.token_urlsafe(24),
    'ReplaceWithStrongDatabasePassword': secrets.token_urlsafe(24),
    'ReplaceWithStrongRedisPassword': secrets.token_urlsafe(24),
    'ReplaceWithAtLeast32CharactersJwtSecret': secrets.token_urlsafe(48),
    'ReplaceWithLongEncryptionMasterKey': secrets.token_urlsafe(48),
    'ReplaceWithStrongAdminPassword': 'Admin@' + secrets.token_urlsafe(18),
}
for k, v in repls.items():
    text = text.replace(k, v)
p.write_text(text, encoding='utf-8')
print('已从 .env.example 生成测试服 .env，并自动替换强密码占位符。')
PY
fi

./deploy/scripts/check-env.sh .env

source .env

echo "停止并清理测试服容器..."
docker compose down --remove-orphans || true
docker rm -f crawler-agent >/dev/null 2>&1 || true

echo "清理测试服数据目录..."
rm -rf ./data/mysql ./data/redis ./data/task-logs ./data/backups ./data/smoke
mkdir -p ./data/mysql ./data/redis ./data/task-logs ./data/backups ./data/smoke
sudo rm -rf /data/crawler-platform/projects /var/lib/crawler-agent 2>/dev/null || rm -rf /data/crawler-platform/projects /var/lib/crawler-agent 2>/dev/null || true
sudo mkdir -p /data/crawler-platform/projects /var/lib/crawler-agent/runs 2>/dev/null || mkdir -p /data/crawler-platform/projects /var/lib/crawler-agent/runs

if [[ "$BUILD" == "1" ]]; then
  if [[ "$PULL" == "1" ]]; then
    docker compose build --pull
  else
    docker compose build
  fi
fi

echo "启动 MySQL / Redis 并执行空库初始化..."
docker compose up -d mysql redis
docker compose run --rm migrate

echo "启动平台服务..."
docker compose up -d api scheduler maintenance web

echo "等待 API 健康检查..."
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${WEB_PORT:-8080}/health" >/dev/null 2>&1; then
    echo "✅ API 健康检查通过：http://127.0.0.1:${WEB_PORT:-8080}/health"
    echo "登录账号：${ADMIN_USERNAME:-admin}"
    echo "登录密码请查看 .env 中 ADMIN_PASSWORD。"
    exit 0
  fi
  sleep 2
done

echo "API 健康检查超时，请查看日志：docker compose logs --tail=300 api" >&2
exit 1
