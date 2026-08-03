#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
. "$ROOT_DIR/deploy/scripts/lib/version.sh"
cd "$ROOT_DIR"

release_env="$(cp_resolve_release_version)"

if [ "${1:-}" = "--export" ]; then
  printf '%s\n' "$release_env"
else
  eval "$release_env"
  printf '%s\n' "$RELEASE_VERSION"
fi
