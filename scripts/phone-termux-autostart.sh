#!/data/data/com.termux/files/usr/bin/bash

export PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
export HOME="${HOME:-/data/data/com.termux/files/home}"
export PATH="$PREFIX/bin:$PATH"

case $- in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

if [ "${ECHO_AUTOSTART_STARTED:-0}" = 1 ]; then
  return 0
fi
export ECHO_AUTOSTART_STARTED=1

if command -v sshd >/dev/null 2>&1 && ! pgrep -x sshd >/dev/null 2>&1; then
  sshd
fi

if [ -x "$HOME/echo-service" ]; then
  "$HOME/echo-service" start >"$HOME/.echo-autostart.log" 2>&1 &
fi
