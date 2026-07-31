#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
[[ -f "$ENV_FILE" ]] && set -a && . "$ENV_FILE" && set +a
errors=(); warnings=()
add_error(){ errors+=("$*"); }
add_warning(){ warnings+=("$*"); }
check_cmd(){ command -v "$1" >/dev/null 2>&1 || add_error "缺少命令：$1"; }
[[ -w "$PROJECT_DIR" ]] || add_error "项目目录不可写：$PROJECT_DIR"
check_cmd curl; check_cmd git; check_cmd docker; check_cmd python3
if command -v docker >/dev/null 2>&1; then docker ps >/dev/null 2>&1 || add_error "Docker 不可用或当前用户无 Docker 权限"; fi
if [[ -n "${CRAWLER_PLATFORM_URL:-}" ]]; then curl -fsS --connect-timeout 5 "${CRAWLER_PLATFORM_URL%/}/health" >/dev/null || add_error "无法访问爬虫平台：${CRAWLER_PLATFORM_URL%/}/health"; else add_error "CRAWLER_PLATFORM_URL 未配置"; fi
[[ -n "${CRAWLER_PLATFORM_DISCOVERY_TOKEN:-}" ]] || add_error "CRAWLER_PLATFORM_DISCOVERY_TOKEN 未配置"
[[ -n "${COMPANY_ID:-}" ]] || add_error "COMPANY_ID 未配置"
[[ -n "${SERVER_CODE:-}" ]] || add_error "SERVER_CODE 未配置"
[[ -n "${IMAGE_REPOSITORY:-}" ]] || add_error "IMAGE_REPOSITORY 未配置"
free_kb=$(df -Pk "$PROJECT_DIR" | awk 'NR==2{print $4+0}')
if (( free_kb < 5*1024*1024 )); then add_warning "项目所在分区剩余空间小于 5GB"; fi
if (( ${#errors[@]} )); then
  echo "❌ 预检失败，共 ${#errors[@]} 项：" >&2
  for item in "${errors[@]}"; do echo " - $item" >&2; done
  if (( ${#warnings[@]} )); then echo "⚠️ 警告：" >&2; for item in "${warnings[@]}"; do echo " - $item" >&2; done; fi
  exit 1
fi
echo "✅ 预检通过：$PROJECT_DIR"
