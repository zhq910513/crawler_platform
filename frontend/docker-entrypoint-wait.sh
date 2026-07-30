#!/bin/sh
set -eu

limit="${WEB_UPSTREAM_WAIT_SECONDS:-180}"
count=0

echo "Waiting for API health at api:8000..."
until wget -q -T 2 -O /dev/null http://api:8000/health >/dev/null 2>&1; do
    count=$((count + 1))
    if [ "$count" -ge "$limit" ]; then
        echo "Timed out waiting for API health after ${limit}s" >&2
        exit 1
    fi
    sleep 1
done

echo "API is healthy."
exec /docker-entrypoint.sh "$@"
