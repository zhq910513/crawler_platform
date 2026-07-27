#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
./deploy/scripts/prepare.sh
docker compose build --no-cache --progress=plain
docker compose up -d
docker compose ps
