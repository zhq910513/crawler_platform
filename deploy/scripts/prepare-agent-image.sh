#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

VERSION=""
REGISTRY_PUBLIC_HOST=""
REGISTRY_PORT=""
RESTART_BACKEND="1"
SKIP_BUILD="0"
SKIP_PUSH="0"
REGISTRY_CONTAINER_NAME="${REGISTRY_CONTAINER_NAME:-crawler-platform-agent-registry}"
REGISTRY_DATA_VOLUME="${REGISTRY_DATA_VOLUME:-crawler-platform-agent-registry-data}"

usage() {
  cat <<USAGE
Usage: bash deploy/scripts/prepare-agent-image.sh [options]

自动准备执行组件镜像：构建、推送到内置 registry、写入 .env 并重启后端服务。

Options:
  --version VERSION              执行组件镜像版本，默认读取 .env AGENT_AGENT_VERSION；Agent 版本独立于平台版本
  --registry-public-host HOST    执行节点访问 registry 使用的主机/IP，默认从 CRAWLER_AGENT_REGISTRY_PUBLIC_HOST、CRAWLER_CONTROL_PUBLIC_BASE_URL 或 CI/CD 注入的 CP_DEPLOY_PUBLIC_HOST 推导
  --registry-port PORT           registry 对外端口，默认读取 CRAWLER_AGENT_REGISTRY_PORT 或 5000
  --no-restart                   只写 .env，不重启 api/scheduler/maintenance
  --skip-build                   跳过 docker build，只使用本地已有 crawler_platform_agent:版本
  --skip-push                    跳过 docker push，只更新 .env
  -h, --help                     查看帮助
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version) VERSION="${2:-}"; shift 2 ;;
    --registry-public-host) REGISTRY_PUBLIC_HOST="${2:-}"; shift 2 ;;
    --registry-port) REGISTRY_PORT="${2:-}"; shift 2 ;;
    --no-restart) RESTART_BACKEND="0"; shift ;;
    --skip-build) SKIP_BUILD="1"; shift ;;
    --skip-push) SKIP_PUSH="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) cp_die "未知参数：$1" ;;
  esac
done

cp_require_docker
[ -f .env ] || cp_die ".env 不存在。请先从 .env.example 初始化并完成基础配置。"

VERSION="${VERSION:-$(cp_env_value .env AGENT_AGENT_VERSION)}"
VERSION="${VERSION:-1.1.1}"
[ -n "$VERSION" ] || cp_die "无法确定 Agent 镜像版本，请配置 AGENT_AGENT_VERSION 或传入 --version。"

REGISTRY_PORT="${REGISTRY_PORT:-$(cp_env_value .env CRAWLER_AGENT_REGISTRY_PORT)}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
case "$REGISTRY_PORT" in
  ''|*[!0-9]*) cp_die "CRAWLER_AGENT_REGISTRY_PORT 必须是数字端口：$REGISTRY_PORT" ;;
esac

extract_host_from_url() {
  printf '%s' "$1" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^\[([^]]+)\].*$#\1#; s#:([0-9]+)$##'
}

REGISTRY_PUBLIC_HOST="${REGISTRY_PUBLIC_HOST:-$(cp_env_value .env CRAWLER_AGENT_REGISTRY_PUBLIC_HOST)}"
if [ -z "$REGISTRY_PUBLIC_HOST" ]; then
  public_base="$(cp_env_value .env CRAWLER_CONTROL_PUBLIC_BASE_URL)"
  public_base="${public_base:-$(cp_env_value .env CONTROL_PLANE_PUBLIC_BASE_URL)}"
  if [ -n "$public_base" ]; then
    REGISTRY_PUBLIC_HOST="$(extract_host_from_url "$public_base")"
  fi
fi
if [ -z "$REGISTRY_PUBLIC_HOST" ] && [ -n "${CP_DEPLOY_PUBLIC_HOST:-}" ]; then
  REGISTRY_PUBLIC_HOST="$(extract_host_from_url "$CP_DEPLOY_PUBLIC_HOST")"
fi

if [ -z "$REGISTRY_PUBLIC_HOST" ] || [ "$REGISTRY_PUBLIC_HOST" = "127.0.0.1" ] || [ "$REGISTRY_PUBLIC_HOST" = "localhost" ] || [ "$REGISTRY_PUBLIC_HOST" = "0.0.0.0" ]; then
  cp_die "无法自动确定执行节点可访问的 registry 主机。CI/CD 请传入 CP_DEPLOY_PUBLIC_HOST，或在 .env 配置 CRAWLER_CONTROL_PUBLIC_BASE_URL / CRAWLER_AGENT_REGISTRY_PUBLIC_HOST。"
fi

LOCAL_IMAGE="crawler_platform_agent:${VERSION}"
LOCAL_REGISTRY="localhost:${REGISTRY_PORT}"
PUBLIC_REGISTRY="${REGISTRY_PUBLIC_HOST}:${REGISTRY_PORT}"
LOCAL_REGISTRY_IMAGE="${LOCAL_REGISTRY}/crawler_platform_agent:${VERSION}"
PUBLIC_AGENT_IMAGE="${PUBLIC_REGISTRY}/crawler_platform_agent:${VERSION}"

cp_info "准备 执行组件镜像：version=${VERSION} publicImage=${PUBLIC_AGENT_IMAGE}"

if docker ps -a --format '{{.Names}}' | grep -qx "$REGISTRY_CONTAINER_NAME"; then
  if [ "$(docker inspect -f '{{.State.Running}}' "$REGISTRY_CONTAINER_NAME" 2>/dev/null || echo false)" != "true" ]; then
    cp_info "启动已有正式 registry 容器：$REGISTRY_CONTAINER_NAME"
    docker start "$REGISTRY_CONTAINER_NAME" >/dev/null
  else
    cp_info "正式 registry 已在运行：$REGISTRY_CONTAINER_NAME"
  fi
else
  legacy_smoke="crawler-platform-smoke-registry"
  if docker ps -a --format '{{.Names}}' | grep -qx "$legacy_smoke" \
    && docker inspect -f '{{.Config.Image}}' "$legacy_smoke" 2>/dev/null | grep -Eq '^registry(:|@)' \
    && docker port "$legacy_smoke" 5000/tcp 2>/dev/null | grep -Eq ":${REGISTRY_PORT}$"; then
    cp_warn "检测到历史 smoke registry 正在承载 ${REGISTRY_PORT}/TCP，原地接管为正式 registry，保留现有镜像数据。"
    docker rename "$legacy_smoke" "$REGISTRY_CONTAINER_NAME"
    docker start "$REGISTRY_CONTAINER_NAME" >/dev/null 2>&1 || true
  else
    port_owner="$(docker ps --format '{{.Names}} {{.Ports}}' | awk -v p=":${REGISTRY_PORT}->5000/tcp" 'index($0,p){print $1; exit}')"
    [ -z "$port_owner" ] || cp_die "${REGISTRY_PORT}/TCP 已被其他容器占用：$port_owner。拒绝把未知容器当成正式 Agent Registry。"
    cp_info "启动正式执行组件镜像仓库：0.0.0.0:${REGISTRY_PORT}->5000，数据卷=${REGISTRY_DATA_VOLUME}"
    docker run -d --restart=always --name "$REGISTRY_CONTAINER_NAME" -p "${REGISTRY_PORT}:5000" -v "${REGISTRY_DATA_VOLUME}:/var/lib/registry" registry:2 >/dev/null
  fi
fi


if [ "$SKIP_BUILD" != "1" ]; then
  cp_info "构建 执行组件镜像：$LOCAL_IMAGE"
  docker build \
    --build-arg "PIP_INDEX_URL=${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}" \
    --build-arg "AGENT_VERSION=${VERSION}" \
    --build-arg "APP_GIT_COMMIT=$(cp_env_value .env APP_GIT_COMMIT)" \
    --build-arg "APP_BUILD_TIME=$(cp_env_value .env APP_BUILD_TIME)" \
    -f agent/Dockerfile \
    -t "$LOCAL_IMAGE" \
    agent
else
  docker image inspect "$LOCAL_IMAGE" >/dev/null 2>&1 || cp_die "--skip-build 需要本地已存在镜像：$LOCAL_IMAGE"
fi

docker tag "$LOCAL_IMAGE" "$LOCAL_REGISTRY_IMAGE"

if [ "$SKIP_PUSH" != "1" ]; then
  cp_info "推送 执行组件镜像到内置 registry：$LOCAL_REGISTRY_IMAGE"
  docker push "$LOCAL_REGISTRY_IMAGE"
else
  cp_warn "已跳过 docker push；请确认 registry 中已有该 tag。"
fi

REGISTRY_TAGS_TMP="/tmp/crawler_agent_registry_tags.$$"
cleanup_prepare_agent_image_tmp() { rm -f "$REGISTRY_TAGS_TMP" ".env.tmp_prepare_agent_image.$$" 2>/dev/null || true; }
trap cleanup_prepare_agent_image_tmp EXIT
if cp_curl_tool -fsS "http://127.0.0.1:${REGISTRY_PORT}/v2/crawler_platform_agent/tags/list" >"$REGISTRY_TAGS_TMP" 2>/dev/null; then
  cp_info "registry tag 验证结果：$(cat "$REGISTRY_TAGS_TMP")"
  if ! grep -Eq '"'"${VERSION}"'"' "$REGISTRY_TAGS_TMP"; then
    cp_die "本机 registry 中未发现 crawler_platform_agent:${VERSION}，请检查 docker push 是否成功。"
  fi
else
  cp_die "本机 registry tag 验证失败：http://127.0.0.1:${REGISTRY_PORT}/v2/crawler_platform_agent/tags/list"
fi

AGENT_IMAGE_DIGEST=""
if docker image inspect "$LOCAL_REGISTRY_IMAGE" >/dev/null 2>&1; then
  AGENT_IMAGE_DIGEST="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$LOCAL_REGISTRY_IMAGE" 2>/dev/null | grep -m1 '@sha256:' | sed 's#^.*@##' || true)"
fi
if [ -n "$AGENT_IMAGE_DIGEST" ]; then
  cp_info "执行组件镜像 digest：$AGENT_IMAGE_DIGEST"
else
  cp_warn "未能从本机镜像读取 RepoDigest；平台自检会继续尝试通过 registry manifest 读取 digest。"
fi

set_env_value() {
  key="$1"; value="$2"
  tmp=".env.tmp_prepare_agent_image.$$"
  awk -v k="$key" -v v="$value" '
    BEGIN { done=0 }
    index($0, k "=") == 1 { print k "=" v; done=1; next }
    { print }
    END { if (!done) print k "=" v }
  ' .env > "$tmp" || return 1
  mv "$tmp" .env
}


backup=".env.bak_prepare_agent_image_$(date +%Y%m%d_%H%M%S)"
cp .env "$backup"
set_env_value AGENT_AGENT_VERSION "$VERSION"
set_env_value CRAWLER_AGENT_IMAGE "$PUBLIC_AGENT_IMAGE"
set_env_value CRAWLER_AGENT_IMAGE_DIGEST "$AGENT_IMAGE_DIGEST"
set_env_value CRAWLER_AGENT_REGISTRY_PUBLIC_HOST "$REGISTRY_PUBLIC_HOST"
set_env_value CRAWLER_AGENT_REGISTRY_PORT "$REGISTRY_PORT"
preserve_env_bool() {
  key="$1"
  current="$(cp_env_value .env "$key")"
  if [ -n "$current" ]; then
    printf '%s
' "$current"
    return 0
  fi
  eval "env_value=\${$key:-}"
  if [ -n "${env_value:-}" ]; then
    printf '%s
' "$env_value"
    return 0
  fi
  printf '0
'
}
set_env_value CRAWLER_AGENT_REGISTRY_AUTH_ENABLED "$(preserve_env_bool CRAWLER_AGENT_REGISTRY_AUTH_ENABLED)"
set_env_value CRAWLER_AGENT_REGISTRY_TLS_ENABLED "$(preserve_env_bool CRAWLER_AGENT_REGISTRY_TLS_ENABLED)"
set_env_value CRAWLER_AGENT_IMAGE_PREPARED_AT "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cp_info ".env 已更新：CRAWLER_AGENT_IMAGE=${PUBLIC_AGENT_IMAGE}（备份：${backup}）"

if [ "$RESTART_BACKEND" = "1" ]; then
  cp_info "重启 API / scheduler / maintenance 使 执行组件镜像配置生效。"
  cp_compose up -d api scheduler maintenance
  web_port="$(cp_env_value .env WEB_PORT)"; web_port="${web_port:-80}"
  if cp_wait_http "http://127.0.0.1:${web_port}/health" 90 2; then
    cp_info "后端健康检查通过，执行组件镜像配置已生效。"
  else
    cp_warn "后端重启后健康检查未确认通过，请执行 docker compose logs --tail=100 api 排查。"
  fi
else
  cp_warn "已跳过后端重启；请稍后执行 docker compose up -d api scheduler maintenance。"
fi

cat <<NEXT

✅ 执行组件镜像分发已准备完成。

平台已自动处理：
- 构建 执行组件镜像
- 推送到内置 registry
- 更新 .env 中的 CRAWLER_AGENT_IMAGE
- $( [ "$RESTART_BACKEND" = "1" ] && printf "重启后端服务使配置生效" || printf "未重启后端服务，请手动重启 api/scheduler/maintenance" )

仍需人工确认：
- 在云防火墙/安全组放行 ${REGISTRY_PORT}/TCP，来源建议限制为执行节点公网 IP。
- 如果使用 HTTP registry，执行节点安装脚本会在授权后自动配置 Docker insecure-registries。

验证命令：
- 控制端本机：curl -i http://127.0.0.1:${REGISTRY_PORT}/v2/
- 执行节点：curl -i http://${PUBLIC_REGISTRY}/v2/
- 执行节点：docker pull ${PUBLIC_AGENT_IMAGE}

NEXT
