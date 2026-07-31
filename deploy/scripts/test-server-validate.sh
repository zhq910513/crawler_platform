#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

YES=0
SKIP_RESET=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --skip-reset) SKIP_RESET=1 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [[ "$YES" != "1" ]]; then
  echo "该脚本会按零数据测试服标准执行验收；默认会清空测试服数据。确认请追加：--yes"
  echo "已有平台已初始化且不想清空时可用：--yes --skip-reset"
  exit 2
fi

if [[ "$SKIP_RESET" != "1" ]]; then
  ./deploy/scripts/reset-test-server.sh --yes
else
  ./deploy/scripts/check-env.sh .env
  docker compose config >/dev/null
  curl -fsS "http://127.0.0.1:${WEB_PORT:-8080}/health" >/dev/null
fi

./deploy/scripts/smoke-test.sh --build-smoke-image --start-agent

echo "✅ 零数据测试服核心验收通过。建议继续执行压测、告警渠道测试和备份恢复演练。"
