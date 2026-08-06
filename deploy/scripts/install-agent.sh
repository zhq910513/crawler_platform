#!/usr/bin/env bash
set -Eeuo pipefail

PLATFORM_URL="${PLATFORM_URL:-}"
JOIN_TOKEN="${JOIN_TOKEN:-}"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:1.0.19}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
FORCE="${FORCE:-0}"
HEALTH_PORT="${AGENT_LOCAL_HEALTH_PORT:-18080}"

while [ $# -gt 0 ]; do
  case "$1" in
    --platform-url) PLATFORM_URL="${2:-}"; shift 2 ;;
    --join-token) JOIN_TOKEN="${2:-}"; shift 2 ;;
    --agent-image) AGENT_IMAGE="${2:-}"; shift 2 ;;
    --force) FORCE="1"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

PASS_COUNT=0; WARN_COUNT=0; FAIL_COUNT=0
pass(){ echo "[PASS] $*"; PASS_COUNT=$((PASS_COUNT+1)); }
warn(){ echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail(){ echo "[FAIL] $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
has_cmd(){ command -v "$1" >/dev/null 2>&1; }

if [ -z "$PLATFORM_URL" ] || [ -z "$JOIN_TOKEN" ]; then fail "必须提供 --platform-url 和 --join-token"; fi
PLATFORM_URL="${PLATFORM_URL%/}"

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
if [ -n "$PLATFORM_URL" ] && has_cmd curl; then
  if curl -fsSL --connect-timeout 5 "$PLATFORM_URL/health" >/dev/null 2>&1 || curl -fsSL --connect-timeout 5 "$PLATFORM_URL/api/v1/agent-bootstrap/ping" >/dev/null 2>&1; then
    pass "平台连通：$PLATFORM_URL"
  else
    fail "无法访问爬虫平台：$PLATFORM_URL，请检查平台 API 端口、防火墙、安全组和路由。"
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
if curl -fsSL -X POST "$PLATFORM_URL/api/v1/agent-bootstrap/env" -H 'Content-Type: application/json' --data "$BODY" > "$ENV_FILE.tmp"; then
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  tmp_env="$ENV_FILE.platform.tmp"
  grep -v '^AGENT_PLATFORM_URL=' "$ENV_FILE" > "$tmp_env" 2>/dev/null || true
  printf "AGENT_PLATFORM_URL='%s'\n" "$PLATFORM_URL" >> "$tmp_env"
  mv "$tmp_env" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  pass "已从平台换取 Agent 配置：$ENV_FILE"
else
  rm -f "$ENV_FILE.tmp"
  fail "换取 Agent 配置失败，joinToken 可能无效、过期或平台不可访问。"
  exit 1
fi

if docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1; then
  pass "Agent 镜像本地已存在：$AGENT_IMAGE"
else
  if docker pull "$AGENT_IMAGE" >/dev/null 2>&1; then pass "Agent 镜像拉取成功：$AGENT_IMAGE"; else warn "Agent 镜像拉取失败：$AGENT_IMAGE。如果本机已有本地构建流程，请先构建后重试。"; fi
fi

docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_ROOT":/data/crawler-agent "$AGENT_IMAGE" >/dev/null
pass "crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
echo "✅ Agent 接入完成。请回到爬虫平台查看心跳、Docker、磁盘、镜像仓库和首次 doctor 结果。"
