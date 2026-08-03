#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics

YES=0
SKIP_RESET=0
AUTO_MIRRORS=0
while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y) YES=1 ;;
    --skip-reset) SKIP_RESET=1 ;;
    --prepare-cn-mirrors) AUTO_MIRRORS=1 ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
  shift
done

if [ "$YES" != "1" ]; then
  echo "该脚本会按零数据测试服标准执行验收；默认会清空测试服数据。确认请追加：--yes"
  echo "已有平台已初始化且不想清空时可用：--yes --skip-reset"
  echo "国内服务器可加：--prepare-cn-mirrors"
  exit 2
fi

cp_fix_project_permissions
./deploy/scripts/doctor.sh
cp_require_docker
cp_warn_cn_mirrors

if [ "$SKIP_RESET" != "1" ]; then
  if [ "$AUTO_MIRRORS" = "1" ]; then
    ./deploy/scripts/reset-test-server.sh --yes --prepare-cn-mirrors
  else
    ./deploy/scripts/reset-test-server.sh --yes
  fi
else
  ./deploy/scripts/check-env.sh .env
  cp_compose config >/dev/null
  WEB_PORT_VALUE="$(cp_env_value .env WEB_PORT)"; WEB_PORT_VALUE="${WEB_PORT_VALUE:-8080}"
  cp_wait_http "http://127.0.0.1:${WEB_PORT_VALUE}/health" 30 2
fi

./deploy/scripts/smoke-test.sh --build-smoke-image --start-agent

echo "✅ 零数据测试服核心验收通过。建议继续执行压测、告警渠道测试和备份恢复演练。"
