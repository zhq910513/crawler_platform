#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
[ -f "$ENV_FILE" ] || { echo "❌ 缺少 .env，请先复制 deploy/.env.example" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a
./deploy/preflight.sh
PLATFORM="${CRAWLER_PLATFORM_URL%/}"
PYTHON_TOOL_IMAGE="${PYTHON_TOOL_IMAGE:-python:3.12-alpine}"
CURL_TOOL_IMAGE="${CURL_TOOL_IMAGE:-curlimages/curl:8.10.1}"
TMP_DIR="$PROJECT_DIR/.crawler_platform_tmp"
mkdir -p "$TMP_DIR"

host_python_ok() {
  command -v python3 >/dev/null 2>&1 && python3 - <<'PYCHECK' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 8) else 1)
PYCHECK
}
run_python() {
  if [ "${CP_USE_HOST_TOOLS:-0}" = "1" ] && host_python_ok; then
    python3 "$@"
  else
    docker run --rm -v "$PROJECT_DIR:$PROJECT_DIR" -w "$PROJECT_DIR" -e PROJECT_DIR -e IMAGE_DIGEST -e GIT_BRANCH -e GIT_COMMIT -e IMAGE_TAG -e PROJECT_KEY -e PROJECT_CODE -e PROJECT_NAME -e IMAGE_REPOSITORY -e RELEASE_VERSION -e RELEASE_CHANNEL -e COMPANY_ID -e SERVER_CODE "$PYTHON_TOOL_IMAGE" python "$@"
  fi
}
curl_file() {
  if command -v curl >/dev/null 2>&1; then
    curl "$@"
  else
    docker run --rm --network host -v "$PROJECT_DIR:$PROJECT_DIR" -w "$PROJECT_DIR" "$CURL_TOOL_IMAGE" "$@"
  fi
}

GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
IMAGE_TAG="${IMAGE_TAG:-${GIT_COMMIT:0:12}}"
if [ "${BUILD_MODE:-local}" = "local" ]; then
  docker build -t "${IMAGE_REPOSITORY}:${IMAGE_TAG}" .
  if [ -n "${REGISTRY_USERNAME:-}" ]; then echo "${REGISTRY_PASSWORD:-}" | docker login "${IMAGE_REPOSITORY%%/*}" -u "$REGISTRY_USERNAME" --password-stdin; fi
  docker push "${IMAGE_REPOSITORY}:${IMAGE_TAG}" || true
fi
DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "${IMAGE_REPOSITORY}:${IMAGE_TAG}" 2>/dev/null | awk -F@ '{print $2}')"
IMAGE_DIGEST="$DIGEST"
export PROJECT_DIR IMAGE_DIGEST GIT_BRANCH GIT_COMMIT IMAGE_TAG
printf '%s' "$DIGEST" | grep -Eq '^sha256:[0-9a-f]{64}$' || { echo "❌ 无法取得有效镜像 digest，请确认镜像已推送到仓库" >&2; exit 1; }

MANIFEST_SCRIPT="$TMP_DIR/parse_discovered_project.py"
MANIFEST_JSON="$TMP_DIR/discovered_project.json"
RESPONSE_JSON="$TMP_DIR/discovered_project_response.json"
cat > "$MANIFEST_SCRIPT" <<'PY'
import ast
import json
import os
import pathlib
import subprocess

root = pathlib.Path(os.environ.get('PROJECT_DIR', '.')).resolve()
required = set(['definitionKey', 'taskName', 'entryModule', 'entryFunction'])

def load_static_tasks(path):
    if not path.exists():
        raise RuntimeError('缺少 sch.py：上线接入要求 sch.py 静态声明 TASKS 任务清单')
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    task_node = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == 'TASKS':
                    task_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'TASKS':
            task_node = node.value
    if task_node is None:
        raise RuntimeError('sch.py 必须声明静态 TASKS = [...]，不能只包含本地执行逻辑')
    try:
        tasks = ast.literal_eval(task_node)
    except Exception as exc:
        raise RuntimeError('TASKS 必须是纯静态字面量，不能调用函数、读取环境变量或动态生成') from exc
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError('TASKS 必须是非空列表')
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            raise RuntimeError('TASKS 第 {} 项必须是字典'.format(index))
        missing = sorted(required - set(task))
        if missing:
            raise RuntimeError('TASKS 第 {} 项缺少字段：{}'.format(index, ', '.join(missing)))
    return tasks

def git_config(args):
    try:
        return subprocess.check_output(args, cwd=str(root), universal_newlines=True).strip()
    except Exception:
        return ''

tasks = load_static_tasks(root / 'sch.py')
manifest = {
  'manifestVersion': '1',
  'projectKey': os.environ.get('PROJECT_KEY') or os.environ.get('PROJECT_CODE'),
  'projectName': os.environ.get('PROJECT_NAME') or os.environ.get('PROJECT_CODE'),
  'projectCode': os.environ.get('PROJECT_CODE'),
  'repositoryUrl': git_config(['git', 'config', '--get', 'remote.origin.url']),
  'imageRepository': os.environ['IMAGE_REPOSITORY'],
  'imageDigest': os.environ['IMAGE_DIGEST'],
  'gitBranch': os.environ.get('GIT_BRANCH', ''),
  'gitCommit': os.environ.get('GIT_COMMIT', ''),
  'releaseVersion': os.environ.get('RELEASE_VERSION') or os.environ.get('IMAGE_TAG'),
  'releaseChannel': os.environ.get('RELEASE_CHANNEL', 'stable'),
  'runtimeType': 'python',
  'taskDefinitions': tasks,
}
payload = {'companyId': int(os.environ['COMPANY_ID']), 'serverCode': os.environ['SERVER_CODE'], 'manifest': manifest}
print(json.dumps(payload, ensure_ascii=False))
PY
PROJECT_DIR="$PROJECT_DIR" IMAGE_DIGEST="$DIGEST" GIT_BRANCH="$GIT_BRANCH" GIT_COMMIT="$GIT_COMMIT" IMAGE_TAG="$IMAGE_TAG" run_python "$MANIFEST_SCRIPT" > "$MANIFEST_JSON"
curl_file -fsS -X POST "$PLATFORM/api/v1/discovered-projects" -H "Authorization: Discovery ${CRAWLER_PLATFORM_DISCOVERY_TOKEN}" -H 'Content-Type: application/json' -d "@$MANIFEST_JSON" > "$RESPONSE_JSON"
run_python -m json.tool "$RESPONSE_JSON" || cat "$RESPONSE_JSON"
echo "✅ 接入上报完成：版本、部署服务器和任务定义已登记；生产调度仍以前端平台配置为准。"
