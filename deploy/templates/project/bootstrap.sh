#!/usr/bin/env bash
set -Eeuo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_DIR"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"
[[ -f "$ENV_FILE" ]] || { echo "❌ 缺少 .env，请先复制 deploy/.env.example" >&2; exit 1; }
set -a; . "$ENV_FILE"; set +a
./deploy/preflight.sh
PLATFORM="${CRAWLER_PLATFORM_URL%/}"
TOKEN_HEADER=( -H "X-Project-Bootstrap-Token: ${PROJECT_BOOTSTRAP_TOKEN}" )
GIT_COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
GIT_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
IMAGE_TAG="${IMAGE_TAG:-${GIT_COMMIT:0:12}}"
if [[ "${BUILD_MODE:-local}" == "local" ]]; then
  docker build -t "${IMAGE_REPOSITORY}:${IMAGE_TAG}" .
  if [[ -n "${REGISTRY_USERNAME:-}" ]]; then echo "${REGISTRY_PASSWORD:-}" | docker login "${IMAGE_REPOSITORY%%/*}" -u "$REGISTRY_USERNAME" --password-stdin; fi
  docker push "${IMAGE_REPOSITORY}:${IMAGE_TAG}" || true
fi
DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "${IMAGE_REPOSITORY}:${IMAGE_TAG}" 2>/dev/null | awk -F@ '{print $2}')"
[[ -n "$DIGEST" ]] || DIGEST="sha256:$(printf '%064d' 0)"
python3 - <<PY >/tmp/crawler_bootstrap_payload.json
import json, os, pathlib
root=pathlib.Path('$PROJECT_DIR')
manifest_path=root/'RELEASE_MANIFEST.json'
project_manifest_path=root/'crawler_project.json'
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {"schema_version":"1.0","app_name":os.environ.get('PROJECT_CODE','customer_spider_project'),"version":"0.0.0","entries":[{"task_name":"system.health","display_name":"health"}]}
project_manifest=json.loads(project_manifest_path.read_text(encoding='utf-8')) if project_manifest_path.exists() else {}
payload={"image_repository":os.environ['IMAGE_REPOSITORY'],"image_tag":os.environ.get('IMAGE_TAG') or '$IMAGE_TAG',"image_digest":"$DIGEST","git_commit":"$GIT_COMMIT","git_branch":"$GIT_BRANCH","server_code":os.environ.get('SERVER_CODE',''),"agent_code":os.environ.get('AGENT_CODE',''),"manifest":manifest,"project_manifest":project_manifest,"import_entries":True}
print(json.dumps(payload,ensure_ascii=False))
PY
curl -fsS -X POST "$PLATFORM/api/bootstrap/spider-release" "${TOKEN_HEADER[@]}" -H 'Content-Type: application/json' -d @/tmp/crawler_bootstrap_payload.json | python3 -m json.tool
echo "✅ bootstrap 完成：版本已登记；真实调度仍以前端平台为准。"
