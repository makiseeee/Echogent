#!/data/data/com.termux/files/usr/bin/bash

case $- in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

if [ -x "$HOME/echo-service" ]; then
  "$HOME/echo-service" start >"$HOME/.echo-autostart.log" 2>&1 &
fi
