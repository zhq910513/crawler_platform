#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR=${INSTALL_DIR:-/opt/crawler-agent}
PYTHON_BIN=${PYTHON_BIN:-python3}

mkdir -p "$INSTALL_DIR" /var/lib/crawler-agent
cp -r crawler_agent requirements.txt .env.example crawler-agent.service.example "$INSTALL_DIR"/

"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install -i https://pypi.tuna.tsinghua.edu.cn/simple -r "$INSTALL_DIR/requirements.txt"

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
  cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
  chmod 600 "$INSTALL_DIR/.env"
fi

cp "$INSTALL_DIR/crawler-agent.service.example" /etc/systemd/system/crawler-agent.service
systemctl daemon-reload
systemctl enable crawler-agent

echo "请先修改 $INSTALL_DIR/.env，然后执行：systemctl restart crawler-agent"
