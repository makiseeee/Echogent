#!/bin/bash
set -euo pipefail

exec /usr/bin/xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox \
  -q "${ECHO_QQ_ACCOUNT:-1812441617}" >>/root/napcat.log 2>&1
