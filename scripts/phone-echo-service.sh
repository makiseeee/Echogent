#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX="/data/data/com.termux/files/usr"
HOME="/data/data/com.termux/files/home"
PATH="$PREFIX/bin"
export PREFIX HOME PATH

SESSION="echo"
PROOT="$PREFIX/bin/proot-distro"
COMMAND=(
  "$PROOT" login
  --bind "$HOME:/mnt/termux-home"
  --work-dir /opt/echo
  ubuntu --
  /usr/bin/env TZ=Asia/Shanghai PYTHONUNBUFFERED=1
  /opt/echo-astrbot/bin/astrbot run
)

case "${1:-status}" in
  start)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "echo already running"
      exit 0
    fi
    printf -v command '%q ' "${COMMAND[@]}"
    tmux new-session -d -s "$SESSION" "$command"
    for _ in $(seq 1 60); do
      if curl -fsS --max-time 2 http://127.0.0.1:6185/ >/dev/null; then
        echo "echo started: http://127.0.0.1:6185"
        exit 0
      fi
      sleep 2
    done
    echo "echo startup timed out" >&2
    tmux capture-pane -pt "$SESSION" -S -80 || true
    exit 1
    ;;
  stop)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      tmux send-keys -t "$SESSION" C-c
      sleep 3
      tmux kill-session -t "$SESSION" 2>/dev/null || true
    fi
    echo "echo stopped"
    ;;
  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "tmux=running"
      curl -sS -o /dev/null -w 'http=%{http_code}\n' --max-time 3 \
        http://127.0.0.1:6185/ || true
    else
      echo "tmux=stopped"
    fi
    ;;
  logs)
    tmux capture-pane -pt "$SESSION" -S -120
    ;;
  *)
    echo "usage: $0 {start|stop|status|logs}" >&2
    exit 2
    ;;
esac
