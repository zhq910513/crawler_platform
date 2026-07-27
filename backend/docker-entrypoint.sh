#!/bin/sh
set -eu

wait_for() {
  host="$1"
  port="$2"
  name="$3"
  limit="${4:-180}"
  count=0

  echo "Waiting for ${name} at ${host}:${port}..."
  until python -c "import socket; s=socket.create_connection(('${host}', ${port}), 2); s.close()" >/dev/null 2>&1; do
    count=$((count + 1))
    if [ "$count" -ge "$limit" ]; then
      echo "Timed out waiting for ${name} at ${host}:${port}" >&2
      exit 1
    fi
    sleep 1
  done
  echo "${name} is reachable."
}

wait_for mysql 3306 MySQL 180
wait_for redis 6379 Redis 180

exec "$@"
