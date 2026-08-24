#!/usr/bin/env bash
set -Eeuo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-}"
JOIN_TOKEN="${JOIN_TOKEN:-}"
AGENT_IMAGE_FROM_ARGS="0"
AGENT_IMAGE="${AGENT_IMAGE:-__CRAWLER_AGENT_IMAGE__}"
AGENT_CONTAINER_NAME="${AGENT_CONTAINER_NAME:-crawler-agent}"
FORCE="${FORCE:-0}"
HEALTH_PORT="${AGENT_LOCAL_HEALTH_PORT:-18080}"
AUTO_CONFIGURE_DOCKER_REGISTRY="${AUTO_CONFIGURE_DOCKER_REGISTRY:-0}"
REPLACE_EXISTING_AGENT="${REPLACE_EXISTING_AGENT:-1}"
CURRENT_STAGE="初始化"
CURL_CONNECT_TIMEOUT="${CRAWLER_AGENT_CURL_CONNECT_TIMEOUT:-3}"
CURL_MAX_TIME="${CRAWLER_AGENT_CURL_MAX_TIME:-10}"
TOKEN_CONSUMED="0"
CREDENTIAL_RESUMED="0"

while [ $# -gt 0 ]; do
  case "$1" in
    --control-plane-url) CONTROL_PLANE_URL="${2:-}"; shift 2 ;;
    --join-token) JOIN_TOKEN="${2:-}"; shift 2 ;;
    --agent-image) AGENT_IMAGE="${2:-}"; AGENT_IMAGE_FROM_ARGS="1"; shift 2 ;;
    --force) FORCE="1"; shift ;;
    --auto-configure-docker-registry) AUTO_CONFIGURE_DOCKER_REGISTRY="1"; shift ;;
    --replace-existing-agent) REPLACE_EXISTING_AGENT="1"; shift ;;
    --no-replace-existing-agent) REPLACE_EXISTING_AGENT="0"; shift ;;
    *) echo "未知参数：$1" >&2; exit 2 ;;
  esac
done

PASS_COUNT=0; WARN_COUNT=0; FAIL_COUNT=0; LAST_FAILURE_REASON=""
stage(){ CURRENT_STAGE="$1"; echo "[STEP] $CURRENT_STAGE"; }
pass(){ echo "[PASS] $*"; PASS_COUNT=$((PASS_COUNT+1)); }
warn(){ echo "[WARN] $*"; WARN_COUNT=$((WARN_COUNT+1)); }
fail(){ LAST_FAILURE_REASON="$*"; echo "[FAIL][$CURRENT_STAGE] $*"; FAIL_COUNT=$((FAIL_COUNT+1)); }
stop(){ echo "[STOP][$CURRENT_STAGE] $*"; }
has_cmd(){ command -v "$1" >/dev/null 2>&1; }
json_escape(){
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}
env_quote(){
  printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\''/g")"
}
report_join_failure(){
  rc="$?"
  # Preflight / STOP before bootstrap credential is issued should not consume or dirty an invitation.
  [ "$TOKEN_CONSUMED" = "1" ] || return 0
  if [ "$rc" != "0" ] && [ -n "${CONTROL_PLANE_URL:-}" ] && [ -n "${JOIN_TOKEN:-}" ] && has_cmd curl; then
    stage_json="$(json_escape "${CURRENT_STAGE:-UNKNOWN}")"
    reason_json="$(json_escape "${LAST_FAILURE_REASON:-安装脚本异常退出}")"
    token_json="$(json_escape "$JOIN_TOKEN")"
    body="{\"joinToken\":\"$token_json\",\"failureStage\":\"$stage_json\",\"failureReason\":\"$reason_json\",\"installReport\":{\"pass\":$PASS_COUNT,\"warn\":$WARN_COUNT,\"fail\":$FAIL_COUNT}}"
    curl -fsS --connect-timeout 1 --max-time 2 -X POST "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/failures" -H 'Content-Type: application/json' --data "$body" >/dev/null 2>&1 || true
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
registry_probe(){
  reg="$1"
  scheme="https"
  registry_likely_http "$reg" && scheme="http"
  url="$scheme://$reg/v2/"
  output="$(curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" "$url" 2>&1)" && { pass "镜像仓库网络可达：$reg"; return 0; }
  fail "执行节点无法访问镜像仓库：$reg；curl：${output:-连接失败或超时}"
  return 1
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
precheck_join_token(){
  [ -n "$JOIN_TOKEN" ] || return 1
  body="{\"joinToken\":\"$(json_escape "$JOIN_TOKEN")\"}"
  curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -X POST "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/precheck" -H 'Content-Type: application/json' --data "$body" >/dev/null
}
configure_insecure_registry(){
  reg="$1"
  docker_insecure_registry_configured "$reg" && { pass "Docker 已允许 HTTP 私有仓库：$reg"; return 0; }
  [ "$AUTO_CONFIGURE_DOCKER_REGISTRY" = "1" ] || { fail "Docker 尚未允许 HTTP 私有仓库：$reg。为避免未经授权修改 daemon.json/重启 Docker，本次安装已停止。"; exit 1; }
  if [ "${CREDENTIAL_RESUMED:-0}" = "1" ]; then
    pass "已复用长期 Agent 凭据，允许继续执行已授权的 Docker Registry 配置"
  else
    stage "Join Token 无副作用预检"
    if precheck_join_token; then
      pass "Join Token 当前有效，允许继续执行已授权的 Docker Registry 配置"
    else
      fail "Join Token 无效或已过期；未修改 Docker daemon.json。请重新生成接入命令。"
      exit 1
    fi
  fi
  stage "Docker HTTP 私有仓库配置"
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
  pass "Docker 已配置 HTTP 私有仓库并重启成功：$reg"
}
platform_run_count(){
  docker ps --filter "label=crawler.platform.run_id" --format '{{.ID}}' 2>/dev/null | wc -l | awk '{print $1+0}'
}
inspect_existing_agent_before_join(){
  if ! docker ps -a --format '{{.Names}}' | grep -qx "$AGENT_CONTAINER_NAME"; then
    return 0
  fi
  existing_running="$(docker inspect -f '{{.State.Running}}' "$AGENT_CONTAINER_NAME" 2>/dev/null || echo false)"
  running_runs="$(platform_run_count)"
  if [ "$REPLACE_EXISTING_AGENT" != "1" ] && [ "$FORCE" != "1" ]; then
    stop "检测到已有 Agent 容器：$AGENT_CONTAINER_NAME。本次未消费 Join Token；如需接管该节点，请使用默认智能替换或移除 --no-replace-existing-agent。"
    exit 2
  fi
  if [ "$existing_running" = "true" ] && [ "${running_runs:-0}" -gt 0 ] && [ "$FORCE" != "1" ]; then
    stop "检测到已有 Agent 正在运行且存在 ${running_runs} 个平台任务容器。本次未消费 Join Token；请等待任务完成后重试。"
    exit 2
  fi
  if [ "$existing_running" = "true" ]; then
    pass "检测到已有 Agent 容器且无平台运行任务，稍后将采用可回滚替换：$AGENT_CONTAINER_NAME"
  else
    pass "检测到已停止的旧 Agent 容器，稍后将自动替换：$AGENT_CONTAINER_NAME"
  fi
}

resume_existing_agent_credential(){
  [ -s "$ENV_FILE" ] || return 1
  # 仅复用平台安装器生成的长期 Agent Credential；失败时不阻断新的 Join 流程。
  set +u
  set -a
  . "$ENV_FILE"
  set +a
  set -u
  existing_token="${AGENT_AGENT_TOKEN:-}"
  [ -n "$existing_token" ] || return 1
  output="$(curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -H "Authorization: Agent $existing_token" "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/resume-env?joinToken=$JOIN_TOKEN" 2>&1)" || {
    warn "检测到本机长期 Agent 凭据但无法用于当前接入命令，将尝试使用本次 Join Token 重新接入：${output:-未知错误}"
    return 1
  }
  printf '%s
' "$output" > "$ENV_FILE.tmp"
  printf 'AGENT_AGENT_TOKEN=%s
' "$(env_quote "$existing_token")" >> "$ENV_FILE.tmp"
  mv "$ENV_FILE.tmp" "$ENV_FILE"
  chmod 600 "$ENV_FILE" 2>/dev/null || true
  requested_agent_image="$AGENT_IMAGE"
  set +u
  set -a
  . "$ENV_FILE"
  set +a
  set -u
  if [ "$AGENT_IMAGE_FROM_ARGS" = "1" ]; then AGENT_IMAGE="$requested_agent_image"; fi
  CREDENTIAL_RESUMED="1"
  pass "已复用本机长期 Agent 凭据，后续失败可继续安装且不消耗新的 Join Token：$ENV_FILE"
  return 0
}

replace_agent_container_with_rollback(){
  backup_name="${AGENT_CONTAINER_NAME}-old-$(date +%Y%m%d%H%M%S)"
  had_existing="0"
  if docker ps -a --format '{{.Names}}' | grep -qx "$AGENT_CONTAINER_NAME"; then
    had_existing="1"
    running="$(docker inspect -f '{{.State.Running}}' "$AGENT_CONTAINER_NAME" 2>/dev/null || echo false)"
    [ "$running" != "true" ] || docker stop -t 20 "$AGENT_CONTAINER_NAME" >/dev/null || { fail "无法停止旧 Agent 容器：$AGENT_CONTAINER_NAME"; return 1; }
    docker rename "$AGENT_CONTAINER_NAME" "$backup_name" >/dev/null || { fail "无法保留旧 Agent 容器副本：$AGENT_CONTAINER_NAME"; return 1; }
  fi
  if docker run -d --name "$AGENT_CONTAINER_NAME" --restart=always --network host --env-file "$ENV_FILE" -e AGENT_HOST_CONFIG_DIR=/var/lib/crawler-agent-host-config -v /var/run/docker.sock:/var/run/docker.sock -v "$AGENT_HOME":/var/lib/crawler-agent-host-config -v "$AGENT_STATE_DIR":/var/lib/crawler-agent -v "$AGENT_PROJECT_ROOT":/data/crawler-agent "$AGENT_IMAGE" >/dev/null; then
    sleep 3
    new_running="$(docker inspect -f '{{.State.Running}}' "$AGENT_CONTAINER_NAME" 2>/dev/null || echo false)"
    if [ "$new_running" = "true" ]; then
      [ "$had_existing" = "0" ] || docker rm -f "$backup_name" >/dev/null 2>&1 || warn "旧 Agent 副本清理失败：$backup_name，可稍后手动删除。"
      return 0
    fi
    fail "新 Agent 容器启动后未保持运行，准备恢复旧容器。"
  else
    fail "Agent 容器启动失败，请检查镜像、Docker 权限和挂载目录。"
  fi
  docker rm -f "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
  if [ "$had_existing" = "1" ]; then
    docker rename "$backup_name" "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
    docker start "$AGENT_CONTAINER_NAME" >/dev/null 2>&1 || true
    warn "已尝试恢复旧 Agent 容器：$AGENT_CONTAINER_NAME"
  fi
  return 1
}

stage "参数校验"
if [ -z "$CONTROL_PLANE_URL" ] || [ -z "$JOIN_TOKEN" ]; then fail "必须提供 --control-plane-url 和 --join-token"; exit 1; fi
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
if [ -n "$CONTROL_PLANE_URL" ] && has_cmd curl; then
  if curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" "$CONTROL_PLANE_URL/health" >/dev/null 2>&1 || curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/ping" >/dev/null 2>&1; then
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

stage "已有 Agent 检查"
inspect_existing_agent_before_join

mkdir -p "$AGENT_HOME" "$AGENT_STATE_DIR" "$AGENT_PROJECT_ROOT" "$AGENT_STATE_DIR/spool" 2>/dev/null || true
stage "长期 Agent 凭据检查"
resume_existing_agent_credential || pass "未发现可复用的长期 Agent 凭据，将使用一次性 Join Token"

stage "执行组件镜像仓库网络检查"
agent_image_first_component="$(image_registry_component "$AGENT_IMAGE")"
if image_has_registry_prefix "$AGENT_IMAGE"; then
  registry_probe "$agent_image_first_component" || true
  if [ "$FAIL_COUNT" -eq 0 ] && registry_likely_http "$agent_image_first_component"; then
    if docker_insecure_registry_configured "$agent_image_first_component"; then
      pass "Docker 已允许 HTTP 私有仓库：$agent_image_first_component"
    else
      warn "Docker 尚未允许 HTTP 私有仓库：$agent_image_first_component；将在长期身份建立后、且仅在明确授权时配置。"
    fi
  fi
else
  warn "执行组件镜像未配置私有仓库前缀，远程节点会默认从 Docker Hub 拉取：$AGENT_IMAGE。"
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
if [ "${CREDENTIAL_RESUMED:-0}" = "1" ]; then
  pass "已复用长期 Agent 凭据，跳过一次性 Join Token 换取配置"
else
  INSTALL_REPORT="{\"installMode\":\"$INSTALL_MODE\",\"pass\":$PASS_COUNT,\"warn\":$WARN_COUNT,\"fail\":$FAIL_COUNT,\"agentHome\":\"$AGENT_HOME\",\"stateDir\":\"$AGENT_STATE_DIR\",\"projectRoot\":\"$AGENT_PROJECT_ROOT\"}"
  BODY="{\"joinToken\":\"$JOIN_TOKEN\",\"hostname\":\"$(hostname 2>/dev/null || echo unknown)\",\"installReport\":$INSTALL_REPORT}"
  if curl -fsS --connect-timeout "$CURL_CONNECT_TIMEOUT" --max-time "$CURL_MAX_TIME" -X POST "$CONTROL_PLANE_URL/api/v1/agent-bootstrap/env" -H 'Content-Type: application/json' --data "$BODY" > "$ENV_FILE.tmp"; then
    TOKEN_CONSUMED="1"
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
    if [ -z "${AGENT_IMAGE:-}" ]; then fail "控制端未下发执行组件镜像地址"; exit 1; fi
    pass "已从控制端换取执行节点配置：$ENV_FILE"
  else
    rm -f "$ENV_FILE.tmp"
    fail "换取 Agent 配置失败，joinToken 可能无效、过期或控制端不可访问。"
    exit 1
  fi
fi
pass "当前接入配置：server=${AGENT_SERVER_CODE:-unknown} agent=${AGENT_AGENT_CODE:-unknown} image=${AGENT_IMAGE:-unknown}"

stage "执行组件镜像仓库确认"
agent_image_first_component="$(image_registry_component "$AGENT_IMAGE")"
if image_has_registry_prefix "$AGENT_IMAGE"; then
  registry_probe "$agent_image_first_component" || { exit 1; }
  if registry_likely_http "$agent_image_first_component" && ! docker_insecure_registry_configured "$agent_image_first_component"; then
    configure_insecure_registry "$agent_image_first_component"
  fi
fi

stage "执行组件镜像拉取"
if docker image inspect "$AGENT_IMAGE" >/dev/null 2>&1; then
  pass "执行组件镜像本地已存在：$AGENT_IMAGE"
else
  pull_output="$(docker pull "$AGENT_IMAGE" 2>&1)" && pull_rc=0 || pull_rc=$?
  if [ "$pull_rc" -eq 0 ]; then
    pass "执行组件镜像拉取成功：$AGENT_IMAGE"
  else
    printf '%s\n' "$pull_output" >&2
    pull_reason="$(printf '%s\n' "$pull_output" | tail -n 5 | tr '\n' ' ' | sed 's/[[:space:]]\+/ /g')"
    fail "执行组件镜像拉取失败：$AGENT_IMAGE；Docker：${pull_reason:-未知错误}"
    exit 1
  fi
fi

stage "启动 Agent 容器"
replace_agent_container_with_rollback || exit 1
pass "crawler-agent 容器已启动：$AGENT_CONTAINER_NAME"
echo "✅ Agent 容器已启动，正在等待首次心跳。请回到控制台确认节点变为在线；如 30 秒后仍接入中，请查看 docker logs --tail 200 $AGENT_CONTAINER_NAME。"
