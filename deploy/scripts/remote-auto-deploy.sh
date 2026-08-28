#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/host.sh"
cd "$ROOT_DIR"

BRANCH="${CP_DEPLOY_BRANCH:-main}"
TARGET_COMMIT="${CP_DEPLOY_COMMIT:-}"
REMOTE="${CP_DEPLOY_REMOTE:-origin}"

cp_info "自动部署入口：remote=${REMOTE} branch=${BRANCH} targetCommit=${TARGET_COMMIT:-<branch-head>}"

if [ ! -d .git ]; then
  cp_die "当前目录不是 Git 仓库：$ROOT_DIR"
  exit 1
fi

cp_ensure_runtime_data_git_excludes

if ! cp_git_restore_mode_only_changes; then
  cp_git_status_filtered >&2 || true
  cp_die "工作区存在真实未提交改动，自动部署已停止。仅文件权限位变化会自动恢复；内容改动、删除或未跟踪文件需要提交、清理或人工确认。"
  exit 1
fi

cp_info "拉取远端引用。"
git fetch "$REMOTE" "$BRANCH" --tags
remote_ref="$REMOTE/$BRANCH"

if ! git rev-parse --verify "$remote_ref" >/dev/null 2>&1; then
  cp_die "远端分支不存在：${remote_ref}"
  exit 1
fi

if [ -n "$TARGET_COMMIT" ]; then
  if ! git merge-base --is-ancestor "$TARGET_COMMIT" "$remote_ref" 2>/dev/null; then
    cp_die "目标 commit ${TARGET_COMMIT} 不在 ${remote_ref} 上，拒绝部署。"
    exit 1
  fi
else
  TARGET_COMMIT="$(git rev-parse "$remote_ref")"
fi

local_ahead="$(git rev-list --count "$remote_ref"..HEAD 2>/dev/null || echo 0)"
if [ "${local_ahead:-0}" != "0" ]; then
  cp_die "测试服本地分支存在未推送提交，拒绝自动部署以避免覆盖：ahead=${local_ahead}。"
  exit 1
fi

cp_info "切换到目标版本：${TARGET_COMMIT}。"
git checkout "$BRANCH"
git reset --hard "$TARGET_COMMIT"

after_commit="$(git rev-parse --short=12 HEAD)"
cp_info "Git 已同步：${after_commit}"

bash deploy/scripts/release-upgrade.sh
