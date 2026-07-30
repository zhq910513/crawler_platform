#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR=${INSTALL_DIR:-/opt/crawler-agent}
STATE_DIR=${STATE_DIR:-/var/lib/crawler-agent}
PYTHON_BIN=${PYTHON_BIN:-python3}
PIP_INDEX_URL=${PIP_INDEX_URL:-https://pypi.org/simple}

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "请使用 root 执行安装脚本。" >&2
  exit 1
fi
for required in crawler_agent requirements.txt .env.example crawler-agent.service.example; do
  if [[ ! -e "$required" ]]; then
    echo "缺少安装文件：$required；请在 agent 目录执行。" >&2
    exit 1
  fi
done
if ! command -v docker >/dev/null 2>&1; then
  echo "未找到 Docker，请先安装并启动 Docker Engine。" >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker 服务不可用，请先启动 Docker。" >&2
  exit 1
fi

install -d -m 0750 -o root -g root "$INSTALL_DIR" "$STATE_DIR" "$STATE_DIR/runs"
rm -rf "$INSTALL_DIR/crawler_agent"
cp -a crawler_agent "$INSTALL_DIR/"
install -m 0640 requirements.txt "$INSTALL_DIR/requirements.txt"
install -m 0640 .env.example "$INSTALL_DIR/.env.example"
install -m 0644 crawler-agent.service.example "$INSTALL_DIR/crawler-agent.service.example"

if [[ ! -x "$INSTALL_DIR/venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
fi
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install --no-cache-dir --index-url "$PIP_INDEX_URL" -r "$INSTALL_DIR/requirements.txt"
"$INSTALL_DIR/venv/bin/python" -m compileall -q "$INSTALL_DIR/crawler_agent"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  install -m 0600 "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
else
  chmod 0600 "$INSTALL_DIR/.env"
fi

install -m 0644 "$INSTALL_DIR/crawler-agent.service.example" /etc/systemd/system/crawler-agent.service
systemctl daemon-reload
systemctl enable crawler-agent

echo "安装完成。修改 $INSTALL_DIR/.env 后执行：systemctl restart crawler-agent"
