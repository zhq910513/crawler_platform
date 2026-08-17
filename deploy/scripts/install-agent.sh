#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-}"
JOIN_TOKEN="${JOIN_TOKEN:-}"
AGENT_IMAGE_FROM_ARGS="0"
AGENT_IMAGE="${AGENT_IMAGE:-crawler_platform_agent:1.0.69}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
FORCE="${FORCE:-0}"
HEALTH_PORT="${AGENT_LOCAL_HEALTH_PORT:-18080}"
AUTO_CONFIGURE_DOCKER_REGISTRY="${AUTO_CONFIGURE_DOCKER_REGISTRY:-0}"
REPLACE_EXISTING_AGENT="${REPLACE_EXISTING_AGENT:-0}"
CURRENT_STAGE="初始化"

while [ $# -gt 0 ]; do
  case "$1" in
    --control-plane-url) CONTROL_PLANE_URL="${2:-}"; shift 2 ;;
    --join-token) JOIN_TOKEN="${2:-}"; shift 2 ;;
    --agent-image) AGENT_IMAGE="${2:-}"; AGENT_IMAGE_FROM_ARGS="1"; shift 2 ;;
    --force) FORCE="1"; shift ;;
    --auto-configure-docker-registry) AUTO_CONFIGURE_DOCKER_REGISTRY="1"; shift ;;
    --replace-existing-agent) REPLACE_EXISTING_AGENT="1"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

PASS_COUNT=0; WARN_COUNT=0; FAIL_COUNT=0; LAST_FAILURE_REASON=""
stage(){ CURRENT_STAGE="$1"; echo "[STEP] $CURRENT_STAGE"; }
pass(){ echo "[PASS] $*"; PASS_COUNT=$((PASS_COUNT+1)); }
warn(){ echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail(){ LAST_FAILURE_REASON="$*"; echo "[FAIL][$CURRENT_STAGE] $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
has_cmd(){ command -v "$1" >/dev/null 2>&1; }
json_escape(){
  printf '%s' "$1" | sed 's/["\]//g'
}
report_join_failure(){
  rc="$?"
  if [ "$rc" != "0" ] && [ -n "${CONTROL_PLANE_URL:-}" ] && [ -n "${JOIN_TOKEN:-}" ] && has_cmd curl; then
    stage_json="$(json_escape "${CURRENT_STAGE:-UNKNOWN}")"
    reason_json="$(json_escape "${LAST_FAILURE_REASON:-安装脚本异常退出}")"
    token_json="$(json_escape "$JOIN_TOKEN")"
    body="{\"joinToken\":\"$token_json\",\"failureStage\":\"$stage_json\",\"failureReason\":\"$reason_json\",\"installReport\":{\"pass\":$PASS_COUNT,\"warn\":$WARN_COUNT,\"fail\":$FAIL_COUNT}}"
    curl -fsSL -X POST "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/failures" -H 'Content-Type: application/json' --data "$body" >/dev/null 2>&1 || true
  fi
}
trap report_join_failure EXIT
run_privileged(){
  if [ "$(id -u 2>/dev/null || echo 1)" = "0" ]; then "$@"; return $?; fi
  if has_cmd sudo; then sudo "$@"; return $?; fi
  return 1
}
image_has_registry_prefix(){
  first="${1%%/*}"
  [ "$first" != "$1" ] && { [ "${first#*.}" != "$first" ] || [ "${first#*:}" != "$first" ] || [ "$first" = "localhost" ]; }
}
image_registry_component(){ printf '%s\n' "${1%%/*}"; }
registry_likely_http(){
  reg="$1"
  host="${reg%%:*}"
  port="${reg##*:}"
  [ "$reg" != "$port" ] || port=""
  [ "$host" = "localhost" ] || [ "$host" = "127.0.0.1" ] || [ "$port" = "5000" ] || [ "$port" = "80" ]
}
docker_insecure_registry_configured(){
  reg="$1"
  docker info 2>/dev/null | grep -F "$reg" >/dev/null 2>&1 && return 0
  [ -r /etc/docker/daemon.json ] && grep -F "\"$reg\"" /etc/docker/daemon.json >/dev/null 2>&1
}
merge_insecure_registry_json(){
  reg="$1"
  if [ ! -s /etc/docker/daemon.json ]; then
    printf '{\n  "insecure-registries": ["%s"]\n}\n' "$reg" | run_privileged tee /etc/docker/daemon.json >/dev/null
    return $?
  fi
  pybin=""
  if has_cmd python3; then pybin="python3"; elif has_cmd python; then pybin="python"; fi
  [ -n "$pybin" ] || return 2
  tmp="/tmp/crawler-agent-daemon.$$.json"
  "$pybin" - "$reg" /etc/docker/daemon.json "$tmp" <<'PYMERGE'
import json, sys
reg, src, dst = sys.argv[1:4]
with open(src, 'r', encoding='utf-8') as f:
    data = json.load(f)
items = data.get('insecure-registries') or []
if not isinstance(items, list):
    raise SystemExit('insecure-registries must be a list')
if reg not in items:
    items.append(reg)
data['insecure-registries'] = items
with open(dst, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write('\n')
PYMERGE
  run_privileged cp "$tmp" /etc/docker/daemon.json
  rc=$?
  rm -f "$tmp"
  return $rc
}
configure_insecure_registry(){
  reg="$1"
  docker_insecure_registry_configured "$reg" && { pass "Docker 已允许 HTTP 私有仓库：$reg"; return 0; }
  [ "$AUTO_CONFIGURE_DOCKER_REGISTRY" = "1" ] || { warn "执行组件镜像仓库 $reg 可能是 HTTP registry；如果 docker pull 失败，请追加 --auto-configure-docker-registry 授权脚本自动备份并配置 Docker insecure-registries。"; return 0; }
  run_privileged mkdir -p /etc/docker || { fail "无法创建 /etc/docker，请使用 root 或 sudo 后重试。"; exit 1; }
  if [ -e /etc/docker/daemon.json ]; then
    backup="/etc/docker/daemon.json.bak_crawler_agent_$(date +%Y%m%d_%H%M%S)"
    run_privileged cp /etc/docker/daemon.json "$backup" || { fail "无法备份 /etc/docker/daemon.json"; exit 1; }
    warn "已备份 Docker 配置：$backup"
  fi
  if merge_insecure_registry_json "$reg"; then
    warn "已写入 Docker insecure-registries：$reg，将重启 Docker 服务。"
  else
    fail "无法安全合并 /etc/docker/daemon.json。请手动加入 insecure-registries：[\"$reg\"] 后重试。"
    exit 1
  fi
  if has_cmd systemctl; then
    run_privileged systemctl restart docker || { fail "Docker 重启失败，请检查 systemctl status docker。"; exit 1; }
  elif has_cmd service; then
    run_privileged service docker restart || { fail "Docker 重启失败，请检查 Docker 服务状态。"; exit 1; }
  else
    fail "未找到 systemctl/service，无法自动重启 Docker。请手动重启 Docker 后重试。"
    exit 1
  fi
  docker info >/dev/null 2>&1 || { fail "Docker 重启后不可用，请检查 Docker 服务和权限。"; exit 1; }
  pass "Docker 已配置并重启，可访问 HTTP 私有仓库：$reg"
}

stage "参数校验"
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

stage "宿主机环境检查"
if has_cmd uname; then pass "系统：$(uname -srm 2>/dev/null || true)"; else warn "未找到 uname"; fi
if has_cmd date; then pass "当前时间：$(date '+%F %T %Z' 2>/dev/null || true)"; fi
if has_cmd curl; then pass "curl 已安装"; else fail "curl 未安装，无法连接平台和下载配置"; fi

stage "控制端连通检查"
# outbound platform check
if [ -n "$CONTROL_PLANE_URL" ] && has_cmd curl; then
  if curl -fsSL --connect-timeout 5 "$CONTROL_PLANE_URL/health" >/dev/null 2>&1 || curl -fsSL --connect-timeout 5 "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/ping" >/dev/null 2>&1; then
    pass "控制端连通：$CONTROL_PLANE_URL"
  else
    fail "无法访问控制端：$CONTROL_PLANE_URL，请检查公网端口、防火墙、安全组和路由。"
  fi
fi

stage "Docker 检查"
if has_cmd docker; then
  pass "Docker 命令存在：$(docker --version 2>/dev/null || true)"
  if docker info >/dev/null 2>&1; then pass "Docker 服务可用且当前用户有权限"; else fail "Docker 服务不可用或当前用户无 Docker 权限"; fi
else
  fail "Docker 未安装，Agent 无法拉取和启动爬虫任务容器"
fi

stage "工作目录与资源检查"
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

stage "安装前检查汇总"
if [ "$FAIL_COUNT" -gt 0 ] && [ "$FORCE" != "1" ]; then
  echo "安装前检查未通过：PASS=$PASS_COUNT WARN=$WARN_COUNT FAIL=$FAIL_COUNT。修复后重试，或追加 --force 强制继续。" >&2
  exit 1
fi

stage "本地目录初始化"
mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_PROJECT_ROOT" "$AGENT_STATE_DIR/spool"
chmod 700 "$AGENT_HOME" "$AGENT_STATE_DIR" 2>/dev/null || true

stage "换取执行节点配置"
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
  if [ -z "${AGENT_IMAGE:-}" ]; then fail "控制端未下发 执行组件镜像地址"; exit 1; fi
  pass "已从控制端换取执行节点配置：$ENV_FILE"
else
  rm -f "$ENV_FILE.tmp"
  fail "换取 Agent 配置失败，joinToken 可能无效、过期或控制端不可访问。"
  exit 1
fi


stage "执行组件镜像仓库检查"
agent_image_first_component="$(image_registry_component "$AGENT_IMAGE")"
if ! image_has_registry_prefix "$AGENT_IMAGE"; then
  warn "执行组件镜像未配置私有仓库前缀，远程节点会默认从 Docker Hub 拉取：$AGENT_IMAGE。生产环境建议配置 CRAWLER_AGENT_IMAGE 为可访问的私有仓库镜像。"
elif registry_likely_http "$agent_image_first_component"; then
  configure_insecure_registry "$agent_image_first_component"
fi

stage "执行组件镜像拉取"
if docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1; then
  pass "执行组件镜像本地已存在：$AGENT_IMAGE"
else
  if docker pull "$AGENT_IMAGE" >/dev/null 2>&1; then
    pass "执行组件镜像拉取成功：$AGENT_IMAGE"
  else
    if image_has_registry_prefix "$AGENT_IMAGE" && registry_likely_http "$agent_image_first_component" && ! docker_insecure_registry_configured "$agent_image_first_component"; then
      fail "执行组件镜像拉取失败且 Docker 未允许 HTTP 私有仓库：$agent_image_first_component。请追加 --auto-configure-docker-registry 授权脚本自动配置，或手动配置 insecure-registries 后重试。"
    else
      fail "执行组件镜像拉取失败且本机不存在：$AGENT_IMAGE。请先配置 CRAWLER_AGENT_IMAGE 为执行节点可访问的私有仓库镜像，或在本机预先构建/加载该镜像后重试。"
    fi
    exit 1
  fi
fi

stage "启动 Agent 容器"
if docker ps -a --format '{{.Names}}' | grep -qx "$AGENT_CONTAINER_NAME"; then
  if [ "$REPLACE_EXISTING_AGENT" = "1" ] || [ "$FORCE" = "1" ]; then
    warn "将替换已有 Agent 容器：$AGENT_CONTAINER_NAME。请确认该节点没有正在运行的关键任务。"
    docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || { fail "无法移除已有 Agent 容器：$AGENT_CONTAINER_NAME"; exit 1; }
  else
    fail "已存在 Agent 容器：$AGENT_CONTAINER_NAME。为避免误中断任务，默认不替换；如确认重新接入，请追加 --replace-existing-agent。"
    exit 1
  fi
fi
docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_ROOT":/data/crawler-agent "$AGENT_IMAGE" >/dev/null || { fail "Agent 容器启动失败，请检查镜像、Docker 权限和挂载目录。"; exit 1; }
pass "crawler-agent 已安装/启动：$AGENT_CONTAINER_NAME"
echo "✅ Agent 接入完成。请回到控制台查看心跳、Docker、磁盘、镜像仓库和首次 doctor 结果。"
