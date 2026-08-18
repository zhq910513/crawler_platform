#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"
cp_trap_diagnostics
bash deploy/scripts/doctor.sh
bash deploy/scripts/prepare.sh
cp_require_docker
cp_warn_cn_mirrors

MYSQL_ID=$(cp_compose ps -q mysql 2>/dev/null || true)
if [ -n "$MYSQL_ID" ] && [ "$(docker inspect -f '{{.State.Running}}' "$MYSQL_ID" 2>/dev/null || true)" = "true" ] && [ "${SKIP_BACKUP:-0}" != "1" ]; then
  bash deploy/scripts/backup.sh
fi

if [ "${NO_CACHE:-0}" = "1" ]; then
  cp_compose build --progress=plain --no-cache
else
  cp_compose build --progress=plain
fi
cp_compose up -d mysql redis
cp_compose run --rm migrate
cp_compose up -d --force-recreate api scheduler maintenance web

PORT="$(cp_env_value .env WEB_PORT)"; PORT="${PORT:-80}"
if cp_wait_http "http://127.0.0.1:${PORT}/health" 120 2; then
  if [ "${AUTO_PREPARE_AGENT_IMAGE:-0}" = "1" ]; then
    if ! bash deploy/scripts/prepare-agent-image.sh; then
      if [ "${STRICT_AGENT_IMAGE_PREPARE:-0}" = "1" ]; then
        cp_die "执行组件镜像自动准备失败，STRICT_AGENT_IMAGE_PREPARE=1 已阻断部署。"
      fi
      cp_warn "执行组件镜像自动准备未完成；请到运行总览查看平台自检并按提示处理。"
    fi
  fi
  bash deploy/scripts/record-platform-preflight-snapshot.sh DEPLOY || true
  cp_compose ps
  echo "crawler_platform 部署完成：http://服务器IP:${PORT}"
  exit 0
fi
cp_compose ps
cp_compose logs --tail=200 api web
cp_die "部署后健康检查失败。"
