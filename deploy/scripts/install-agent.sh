#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-}"
JOIN_TOKEN="${JOIN_TOKEN:-}"
AGENT_IMAGE_FROM_ARGS="0"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:1.0.52}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
FORCE="${FORCE:-0}"
HEALTH_PORT="${AGENT_LOCAL_HEALTH_PORT:-18080}"

while [ $# -gt 0 ]; do
  case "$1" in
    --control-plane-url) CONTROL_PLANE_URL="${2:-}"; shift 2 ;;
    --join-token) JOIN_TOKEN="${2:-}"; shift 2 ;;
    --agent-image) AGENT_IMAGE="${2:-}"; AGENT_IMAGE_FROM_ARGS="1"; shift 2 ;;
    --force) FORCE="1"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

PASS_COUNT=0; WARN_COUNT=0; FAIL_COUNT=0
pass(){ echo "[PASS] $*"; PASS_COUNT=$((PASS_COUNT+1)); }
warn(){ echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail(){ echo "[FAIL] $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
has_cmd(){ command -v "$1" >/dev/null 2>&1; }

if [ -z "$CONTROL_PLANE_URL" ] || [ -z "$JOIN_TOKEN" ]; then fail "必须提供 --control-plane-url 和 --join-token"; fi
CONTROL_PLANE_URL="${CONTROL_PLANE_URL%/}"

if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then
  INSTALL_MODE="root"
  AGENT_HOME="${AGENT_HOME:-/opt/crawler-agent}"
  AGENT_STATE_DIR="${AGENT_STATE_DIR:-/var/lib/crawler-agent}"
  AGENT_PROJECT_ROOT="${AGENT_PROJECT_ROOT:-/data/crawler-agent}"
else
  INSTALL_MODE="user"
  AGENT_HOME="${AGENT_HOME:-$HOME/.crawler-agent}"
  AGENT_STATE_DIR="${AGENT_STATE_DIR:-$HOME/.local/state/crawler-agent}"
  AGENT_PROJECT_ROOT="${AGENT_PROJECT_ROOT:-$HOME/.local/share/crawler-agent}"
  warn "当前非 root，采用用户级目录；必须确保当前用户有 Docker 权限。"
fi
ENV_FILE="${ENV_FILE:-$AGENT_HOME/.env}"

if has_cmd uname; then pass "系统：$(uname -srm 2>/dev/null || true)"; else warn "未找到 uname"; fi
if has_cmd date; then pass "当前时间：$(date '+%F %T %Z' 2>/dev/null || true)"; fi
if has_cmd curl; then pass "curl 已安装"; else fail "curl 未安装，无法连接平台和下载配置"; fi

# outbound platform check
if [ -n "$CONTROL_PLANE_URL" ] && has_cmd curl; then
  if curl -fsSL --connect-timeout 5 "$CONTROL_PLANE_URL/health" >/dev/null 2>&1 || curl -fsSL --connect-timeout 5 "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/ping" >/dev/null 2>&1; then
    pass "控制端连通：$CONTROL_PLANE_URL"
  else
    fail "无法访问控制端：$CONTROL_PLANE_URL，请检查公网端口、防火墙、安全组和路由。"
  fi
fi

if has_cmd docker; then
  pass "Docker 命令存在：$(docker --version 2>/dev/null || true)"
  if docker info >/dev/null 2>&1; then pass "Docker 服务可用且当前用户有权限"; else fail "Docker 服务不可用或当前用户无 Docker 权限"; fi
else
  fail "Docker 未安装，Agent 无法拉取和启动爬虫任务容器"
fi

if has_cmd df; then
  mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_PROJECT_ROOT" 2>/dev/null || true
  if [ -w "$AGENT_HOME" ] && [ -w "$AGENT_STATE_DIR" ] && [ -w "$AGENT_PROJECT_ROOT" ]; then pass "工作目录可写：$AGENT_HOME / $AGENT_STATE_DIR / $AGENT_PROJECT_ROOT"; else fail "工作目录不可写，请调整 AGENT_HOME/AGENT_STATE_DIR/AGENT_PROJECT_ROOT 或使用有权限用户"; fi
  avail_kb=$(df -Pk "$AGENT_PROJECT_ROOT" 2>/dev/null | awk 'NR==2{print $4+0}')
  if [ "${avail_kb:-0}" -lt 3145728 ]; then fail "项目工作目录剩余空间小于 3GB"; elif [ "${avail_kb:-0}" -lt 10485760 ]; then warn "项目工作目录剩余空间小于 10GB"; else pass "磁盘空间充足"; fi
fi

if has_cmd ss; then
  if ss -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$HEALTH_PORT$"; then warn "本机健康端口 $HEALTH_PORT 已被占用，Agent 将不会默认开放公网端口。"; else pass "本机健康端口 $HEALTH_PORT 未占用"; fi
elif has_cmd netstat; then
  if netstat -lnt 2>/dev/null | awk '{print $4}' | grep -Eq "[:.]$HEALTH_PORT$"; then warn "本机健康端口 $HEALTH_PORT 已被占用"; else pass "本机健康端口 $HEALTH_PORT 未占用"; fi
else
  warn "未找到 ss/netstat，跳过本机端口占用检测"
fi

if [ "$FAIL_COUNT" -gt 0 ] && [ "$FORCE" != "1" ]; then
  echo "安装前检查未通过：PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT。修复后重试，或追加 --force 强制继续。" >&2
  exit 1
fi

mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_PROJECT_ROOT" "$AGENT_STATE_DIR/spool"
chmod 700 "$AGENT_HOME" "$AGENT_STATE_DIR" 2>/dev/null || true

INSTALL_REPORT="{\"installMode\":\"$INSTALL_MODE\",\"pass\":$PASS_COUNT,\"warn\":$WARN_COUNT,\"fail\":$FAIL_COUNT,\"agentHome\":\"$AGENT_HOME\",\"stateDir\":\"$AGENT_STATE_DIR\",\"projectRoot\":\"$AGENT_PROJECT_ROOT\"}"
BODY="{\"joinToken\":\"$JOIN_TOKEN\",\"hostname\":\"$(hostname 2>/dev/null || echo unknown)\",\"installReport\":$INSTALL_REPORT}"
if curl -fsSL -X POST "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/env" -H 'Content-Type: application/json' --data "$BODY" > "$ENV_FILE.tmp"; then
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  tmp_env="$ENV_FILE.platform.tmp"
  grep -v '^AGENT_CONTROL_PLANE_URL=' "$ENV_FILE" > "$tmp_env" 2>/dev/null || true
  printf "AGENT_CONTROL_PLANE_URL='%s'\n" "$CONTROL_PLANE_URL" >> "$tmp_env"
  mv "$tmp_env" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  requested_agent_image="$AGENT_IMAGE"
  set -a
  . "$ENV_FILE"
  set +a
  if [ "$AGENT_IMAGE_FROM_ARGS" = "1" ]; then AGENT_IMAGE="$requested_agent_image"; fi
  if [ -z "${AGENT_IMAGE:-}" ]; then fail "控制端未下发 Agent 镜像地址"; exit 1; fi
  pass "已从控制端换取执行节点配置：$ENV_FILE"
else
  rm -f "$ENV_FILE.tmp"
  fail "换取 Agent 配置失败，joinToken 可能无效、过期或控制端不可访问。"
  exit 1
fi


agent_image_first_component="${AGENT_IMAGE%%/*}"
if [ "$agent_image_first_component" = "$AGENT_IMAGE" ] || { [ "${agent_image_first_component#*.}" = "$agent_image_first_component" ] && [ "${agent_image_first_component#*:}" = "$agent_image_first_component" ] && [ "$agent_image_first_component" != "localhost" ]; }; then
  warn "Agent 镜像未配置私有仓库前缀，远程节点会默认从 Docker Hub 拉取：$AGENT_IMAGE。生产环境建议配置 CRAWLER_AGENT_IMAGE 为可访问的私有仓库镜像。"
fi

if docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1; then
  pass "Agent 镜像本地已存在：$AGENT_IMAGE"
else
  if docker pull "$AGENT_IMAGE" >/dev/null 2>&1; then
    pass "Agent 镜像拉取成功：$AGENT_IMAGE"
  else
    fail "Agent 镜像拉取失败且本机不存在：$AGENT_IMAGE。请先配置 CRAWLER_AGENT_IMAGE 为执行节点可访问的私有仓库镜像，或在本机预先构建/加载该镜像后重试。"
    exit 1
  fi
fi

docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_ROOT":/data/crawler-agent "$AGENT_IMAGE" >/dev/null
pass "crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
echo "✅ Agent 接入完成。请回到控制台查看心跳、Docker、磁盘、镜像仓库和首次 doctor 结果。"
