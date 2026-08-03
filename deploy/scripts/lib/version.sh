#!/usr/bin/env bash
# Common release-version helpers for crawler_platform.
# This file is intentionally Bash 4.2 compatible and does not depend on host Python/npm/jq.

cp_normalize_version() {
  printf '%s' "${1:-}" | sed -nE 's/^v?([0-9]+\.[0-9]+\.[0-9]+)$/\1/p' | head -n 1
}

cp_extract_version_from_text() {
  printf '%s\n' "${1:-}" | sed -nE 's/.*(^|[^0-9])v?([0-9]+\.[0-9]+\.[0-9]+)([^0-9]|$).*/\2/p' | head -n 1
}

cp_resolve_release_version() {
  local release_version="" version_source="" tag_version="" commit_subject="" commit_version="" file_version="" git_commit="unknown"

  if [ -d .git ] && command -v git >/dev/null 2>&1; then
    tag_version="$(git tag --points-at HEAD 2>/dev/null | while IFS= read -r tag; do cp_normalize_version "$tag"; done | head -n 1 || true)"
    if [ -n "$tag_version" ]; then
      release_version="$tag_version"
      version_source="git_tag"
    fi

    if [ -z "$release_version" ]; then
      commit_subject="$(git log -1 --pretty=%s 2>/dev/null || true)"
      commit_version="$(cp_extract_version_from_text "$commit_subject")"
      if [ -n "$commit_version" ]; then
        release_version="$commit_version"
        version_source="git_commit_subject"
      fi
    fi

    git_commit="$(git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
  fi

  if [ -z "$release_version" ] && [ -f VERSION ]; then
    file_version="$(cp_normalize_version "$(tr -d '[:space:]' < VERSION)")"
    if [ -n "$file_version" ]; then
      release_version="$file_version"
      version_source="VERSION"
    fi
  fi

  if [ -z "$release_version" ]; then
    echo "无法解析发布版本：请给当前 commit 打 vX.Y.Z tag，或在最新 commit message / VERSION 文件中写明 X.Y.Z。" >&2
    return 1
  fi

  printf 'RELEASE_VERSION=%s\n' "$release_version"
  printf 'RELEASE_VERSION_SOURCE=%s\n' "$version_source"
  printf 'RELEASE_GIT_COMMIT=%s\n' "$git_commit"
}

cp_runtime_metadata_json() {
  local app_name="$1" version="$2" git_commit="$3" build_time="$4"
  printf '{\n  "appName": "%s",\n  "version": "%s",\n  "gitCommit": "%s",\n  "buildTime": "%s"\n}\n' "$app_name" "$version" "$git_commit" "$build_time"
}
