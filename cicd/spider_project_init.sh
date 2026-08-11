#!/usr/bin/env sh
set -eu
provider="${1:-__CRAWLER_CI_PROVIDER__}"
control_base_url="__CRAWLER_CONTROL_BASE_URL__"
force="${CRAWLER_PLATFORM_INIT_FORCE:-0}"
company_code="${CRAWLER_COMPANY_CODE:-${COMPANY_CODE:-__CRAWLER_COMPANY_CODE__}}"
project_code="${CRAWLER_PROJECT_CODE:-${PROJECT_CODE:-$(basename "$PWD" | tr -c 'A-Za-z0-9_.-' '-' | sed 's/^-*//;s/-*$//')}}"
project_name="${CRAWLER_PROJECT_NAME:-${PROJECT_NAME:-$project_code}}"
release_channel="${CRAWLER_RELEASE_CHANNEL:-${CRAWLER_PLATFORM_RELEASE_CHANNEL:-${RELEASE_CHANNEL:-stable}}}"
case "$control_base_url" in http://*|https://*) ;; *) echo "初始化脚本缺少有效控制端公网回调地址，请从平台的 CI一键初始化 页面复制命令。" >&2; exit 2 ;; esac
if [ -z "$company_code" ]; then echo "缺少 companyCode。请从平台对应公司页面复制 CI 一键初始化命令。" >&2; exit 2; fi
control_base_url="${control_base_url%/}"
write_workflow() {
  template_url="$1"
  target="$2"
  tmp="$(mktemp)"
  curl -fsSL "$template_url" -o "$tmp"
  awk -v base="$control_base_url" '{gsub(/__CRAWLER_CONTROL_BASE_URL__/, base); print}' "$tmp" > "$target"
  rm -f "$tmp"
  echo "已生成 $target"
}
case "$provider" in
  github|gha)
    mkdir -p .github/workflows
    target=".github/workflows/crawler-platform-spider-release.yml"
    if [ -f "$target" ] && [ "$force" != "1" ]; then echo "$target 已存在。如需覆盖：CRAWLER_PLATFORM_INIT_FORCE=1" >&2; exit 3; fi
    write_workflow "$control_base_url/api/v1/cicd/templates/github-actions-spider-release.yml" "$target"
    ;;
  gitlab)
    target=".gitlab-ci.yml"
    if [ -f "$target" ] && [ "$force" != "1" ]; then echo "$target 已存在。如需覆盖：CRAWLER_PLATFORM_INIT_FORCE=1" >&2; exit 3; fi
    write_workflow "$control_base_url/api/v1/cicd/templates/gitlab-ci-spider-release.yml" "$target"
    ;;
  *) echo "用法：从平台 CI一键初始化 页面复制命令：curl -fsSL '<控制端>/api/v1/cicd/spider-project-init.sh?provider=github&companyCode=xxx' | sh" >&2; exit 2 ;;
esac
if [ ! -f crawler_project.json ] || [ "$force" = "1" ]; then cat > crawler_project.json <<JSON
{
  "companyCode": "$company_code",
  "projectCode": "$project_code",
  "projectName": "$project_name",
  "releaseChannel": "$release_channel"
}
JSON
  echo "已生成 crawler_project.json"
fi
if [ ! -f VERSION ]; then printf '1.0.0\n' > VERSION; echo "已生成 VERSION，请按项目真实版本调整"; fi
if [ ! -f sch.py ] && [ ! -f crawler_manifest.json ]; then cat > sch.py <<'PY'
# 静态任务定义。CI 只解析 TASKS，不 import 业务代码。
TASKS = [
    {
        "definitionKey": "demo_task",
        "taskName": "示例任务",
        "entryModule": "spiders.demo_task",
        "entryFunction": "main",
    }
]
PY
  echo "已生成 sch.py 示例，请替换为项目真实任务定义"
fi
echo "下一步：git add . && git commit -m '接入 crawler platform 自动构建发布' && git push"
