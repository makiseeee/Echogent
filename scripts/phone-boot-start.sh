#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX="/data/data/com.termux/files/usr"
HOME="/data/data/com.termux/files/home"
PATH="$PREFIX/bin"
export PREFIX HOME PATH

"$PREFIX/bin/termux-wake-lock" || true
"$HOME/echo-service" start
