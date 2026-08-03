#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"
obsolete="backend/migrations/versions/0002_platform_1_0_2_observability.py backend/migrations/versions/0003_expand_schedule_cron_expression.py"
removed=0
for file in $obsolete; do
  if [ -e "$file" ]; then
    rm -f "$file"
    printf '已删除废弃迁移文件：%s\n' "$file"
    removed=1
  fi
done
if [ "$removed" -eq 0 ]; then
  printf '未发现废弃迁移文件。\n'
fi
printf '当前迁移文件：\n'
find backend/migrations/versions -maxdepth 1 -type f -name '*.py' -printf '%f\n' | sort
printf '\n请执行：git add -A backend/migrations/versions deploy/scripts && git status --short\n'
