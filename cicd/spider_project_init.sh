#!/usr/bin/env sh
set -eu
provider="${1:-github}"
platform_url="${CRAWLER_PLATFORM_URL:-${PLATFORM_URL:-}}"
force="${CRAWLER_PLATFORM_INIT_FORCE:-0}"
company_code="${CRAWLER_COMPANY_CODE:-${COMPANY_CODE:-}}"
project_code="${CRAWLER_PROJECT_CODE:-${PROJECT_CODE:-$(basename "$PWD" | tr -c 'A-Za-z0-9_.-' '-' | sed 's/^-*//;s/-*$//')}}"
project_name="${CRAWLER_PROJECT_NAME:-${PROJECT_NAME:-$project_code}}"
release_channel="${CRAWLER_PLATFORM_RELEASE_CHANNEL:-${RELEASE_CHANNEL:-stable}}"
if [ -z "$platform_url" ]; then echo "缺少 CRAWLER_PLATFORM_URL 或 PLATFORM_URL" >&2; exit 2; fi
if [ -z "$company_code" ]; then echo "缺少 CRAWLER_COMPANY_CODE。不同公司项目放在同一个个人 GitHub 下时，必须在 crawler_project.json 声明公司编码。" >&2; exit 2; fi
platform_url="${platform_url%/}"
case "$provider" in
  github|gha)
    mkdir -p .github/workflows
    target=".github/workflows/crawler-platform-spider-release.yml"
    if [ -f "$target" ] && [ "$force" != "1" ]; then echo "$target 已存在。如需覆盖：CRAWLER_PLATFORM_INIT_FORCE=1" >&2; exit 3; fi
    curl -fsSL "$platform_url/api/v1/cicd/templates/github-actions-spider-release.yml" -o "$target"
    echo "已生成 $target"
    ;;
  gitlab)
    target=".gitlab-ci.yml"
    if [ -f "$target" ] && [ "$force" != "1" ]; then echo "$target 已存在。如需覆盖：CRAWLER_PLATFORM_INIT_FORCE=1" >&2; exit 3; fi
    curl -fsSL "$platform_url/api/v1/cicd/templates/gitlab-ci-spider-release.yml" -o "$target"
    echo "已生成 $target"
    ;;
  *) echo "用法：CRAWLER_PLATFORM_URL=https://platform.example.com CRAWLER_COMPANY_CODE=company_code sh -s -- github|gitlab" >&2; exit 2 ;;
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
