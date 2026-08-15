#!/usr/bin/env bash
set -euo pipefail

MIRROR="http://mirrors.tuna.tsinghua.edu.cn/ubuntu-ports"
APT_SOURCE="/etc/apt/sources.list.d/ubuntu.sources"
VENV="/opt/echo-astrbot"
PYPI="https://pypi.tuna.tsinghua.edu.cn/simple"

if [ -f "$APT_SOURCE" ]; then
  sed -i -E \
    "s#https?://(ports.ubuntu.com/ubuntu-ports|mirrors.tuna.tsinghua.edu.cn/ubuntu-ports)#$MIRROR#g" \
    "$APT_SOURCE"
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git python3.12 python3.12-venv

python3.12 -m venv "$VENV"
"$VENV/bin/python" -m pip install --index-url "$PYPI" --upgrade pip uv
"$VENV/bin/uv" pip install \
  --python "$VENV/bin/python" \
  --index-url "$PYPI" \
  --link-mode copy \
  "AstrBot==4.27.2"

echo "AstrBot installed in $VENV"
"$VENV/bin/python" -c 'import astrbot; print("AstrBot import ok")'
