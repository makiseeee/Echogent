#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX="/data/data/com.termux/files/usr"
HOME="/data/data/com.termux/files/home"
PATH="$PREFIX/bin"
export PREFIX HOME PATH

"$PREFIX/bin/termux-wake-lock" || true
if ! pgrep -x sshd >/dev/null 2>&1; then
  "$PREFIX/bin/sshd"
fi
"$HOME/echo-service" start
