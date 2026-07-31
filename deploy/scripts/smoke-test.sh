#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
exec docker run --rm -v "$PWD":"$PWD" -w "$PWD" -v /var/run/docker.sock:/var/run/docker.sock python:3.12-alpine sh -lc 'apk add --no-cache docker-cli curl >/dev/null && python deploy/scripts/smoke-test.py "$@"' smoke-test "$@"
