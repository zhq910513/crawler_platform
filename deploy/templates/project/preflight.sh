#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
[ -f "$ENV_FILE" ] && set -a && . "$ENV_FILE" && set +a
errors=""
warnings=""
add_error(){ errors="${errors}
 - $*"; }
add_warning(){ warnings="${warnings}
 - $*"; }
has_cmd(){ command -v "$1" >/dev/null 2>&1; }
check_optional(){ has_cmd "$1" || add_warning "宿主机缺少可选命令：$1；流程会尽量使用 Docker 工具容器或降级处理"; }

[ -w "$PROJECT_DIR" ] || add_error "项目目录不可写：$PROJECT_DIR"
has_cmd docker || add_error "缺少最低依赖：docker"
if has_cmd docker; then docker ps >/dev/null 2>&1 || add_error "Docker 不可用或当前用户无 Docker 权限"; fi
check_optional curl
check_optional git
check_optional python3

if [ -n "${CRAWLER_PLATFORM_URL:-}" ]; then
  if has_cmd curl; then
    curl -fsS --connect-timeout 5 "${CRAWLER_PLATFORM_URL%/}/health" >/dev/null || add_error "无法访问爬虫平台：${CRAWLER_PLATFORM_URL%/}/health"
  else
    docker run --rm --network host curlimages/curl:8.10.1 -fsS --connect-timeout 5 "${CRAWLER_PLATFORM_URL%/}/health" >/dev/null || add_error "无法通过 curl 工具容器访问爬虫平台：${CRAWLER_PLATFORM_URL%/}/health"
  fi
else
  add_error "CRAWLER_PLATFORM_URL 未配置"
fi
[ -n "${CRAWLER_PLATFORM_DISCOVERY_TOKEN:-}" ] || add_error "CRAWLER_PLATFORM_DISCOVERY_TOKEN 未配置"
[ -n "${COMPANY_ID:-}" ] || add_error "COMPANY_ID 未配置"
[ -n "${SERVER_CODE:-}" ] || add_error "SERVER_CODE 未配置"
[ -n "${IMAGE_REPOSITORY:-}" ] || add_error "IMAGE_REPOSITORY 未配置"
free_kb=$(df -Pk "$PROJECT_DIR" | awk 'NR==2{print $4+0}')
if [ "$free_kb" -lt 5242880 ]; then add_warning "项目所在分区剩余空间小于 5GB；不阻断预检，但镜像构建可能失败"; fi
if [ -n "$errors" ]; then
  echo "❌ 预检失败：最低接入条件不满足" >&2
  printf '%s\n' "$errors" >&2
  if [ -n "$warnings" ]; then echo "⚠️ 警告：" >&2; printf '%s\n' "$warnings" >&2; fi
  exit 1
fi
if [ -n "$warnings" ]; then echo "⚠️ 预检警告，不阻断接入流程：" >&2; printf '%s\n' "$warnings" >&2; fi
echo "✅ 预检通过：最低接入条件满足，warnings 不会打断流程。"
