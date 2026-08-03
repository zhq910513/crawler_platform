#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

normalize_version() {
  printf '%s' "${1:-}" | sed -nE 's/^v?([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' | head -n 1
}

extract_version_from_text() {
  printf '%s\n' "${1:-}" | sed -nE 's/.*(^|[^0-9])v?([0-9]+\.[0-9]+\.[0-9]+)([^0-9]|$).*/\2/p' | head -n 1
}

version_source=""
release_version=""

if [ -d .git ] && command -v git >/dev/null 2>&1; then
  tag_version="$(git tag --points-at HEAD 2>/dev/null | while IFS= read -r tag; do normalize_version "$tag"; done | head -n 1 || true)"
  if [ -n "$tag_version" ]; then
    release_version="$tag_version"
    version_source="git_tag"
  fi

  if [ -z "$release_version" ]; then
    commit_subject="$(git log -1 --pretty=%s 2>/dev/null || true)"
    commit_version="$(extract_version_from_text "$commit_subject")"
    if [ -n "$commit_version" ]; then
      release_version="$commit_version"
      version_source="git_commit_subject"
    fi
  fi
fi

if [ -z "$release_version" ] && [ -f VERSION ]; then
  file_version="$(normalize_version "$(tr -d '[:space:]' < VERSION)")"
  if [ -n "$file_version" ]; then
    release_version="$file_version"
    version_source="VERSION"
  fi
fi

if [ -z "$release_version" ]; then
  echo "无法解析发布版本：请给当前 commit 打 vX.Y.Z tag，或在最新 commit message / VERSION 文件中写明 X.Y.Z。" >&2
  exit 1
fi

git_commit="unknown"
if [ -d .git ] && command -v git >/dev/null 2>&1; then
  git_commit="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
fi

if [ "${1:-}" = "--export" ]; then
  printf 'RELEASE_VERSION=%s\n' "$release_version"
  printf 'RELEASE_VERSION_SOURCE=%s\n' "$version_source"
  printf 'RELEASE_GIT_COMMIT=%s\n' "$git_commit"
else
  printf '%s\n' "$release_version"
fi
