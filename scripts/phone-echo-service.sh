#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX="/data/data/com.termux/files/usr"
HOME="/data/data/com.termux/files/home"
PATH="$PREFIX/bin"
export PREFIX HOME PATH

# Runtime-only credentials live outside the repository and deployment bundle.
SECRETS_FILE="$HOME/.echo-secrets"
if [ -r "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  . "$SECRETS_FILE"
fi

SESSION="echo"
NAPCAT_SESSION="napcat"
MEMORY_SESSION="memory-daily"
MEMORY_SCRIPT="$HOME/echo-memory/scripts/memory-daily-loop.sh"
PROOT="$PREFIX/bin/proot-distro"
NAPCAT_SCRIPT="$HOME/phone-napcat-start.sh"
COMMAND=(
  "$PROOT" login
  --bind "$HOME:/mnt/termux-home"
  --work-dir /opt/echo
  ubuntu --
  /usr/bin/env TZ=Asia/Shanghai PYTHONUNBUFFERED=1
  "ECHO_HAJIMI_API_KEY=${ECHO_HAJIMI_API_KEY:-}"
  "ECHO_SILICONFLOW_API_KEY=${ECHO_SILICONFLOW_API_KEY:-}"
  "ECHO_STT_MODEL=${ECHO_STT_MODEL:-FunAudioLLM/SenseVoiceSmall}"
  /opt/echo-astrbot/bin/astrbot run
)
NAPCAT_COMMAND=(
  "$PROOT" login
  --bind "$HOME:/mnt/termux-home"
  ubuntu --
  /mnt/termux-home/phone-napcat-start.sh
)

stop_napcat_processes() {
  "$PROOT" login ubuntu -- /bin/bash -lc \
    "pkill -TERM -f '/root/Napcat/opt/QQ/[q]q' 2>/dev/null || true; pkill -TERM -x Xvfb 2>/dev/null || true" \
    >/dev/null 2>&1 || true
}

start_napcat() {
  if [ -x "$NAPCAT_SCRIPT" ] && ! tmux has-session -t "$NAPCAT_SESSION" 2>/dev/null; then
    stop_napcat_processes
    printf -v napcat_command '%q ' "${NAPCAT_COMMAND[@]}"
    tmux new-session -d -s "$NAPCAT_SESSION" "$napcat_command"
  fi
}

start_memory_daily() {
  if [ -x "$MEMORY_SCRIPT" ] && ! tmux has-session -t "$MEMORY_SESSION" 2>/dev/null; then
    tmux new-session -d -s "$MEMORY_SESSION" "$MEMORY_SCRIPT"
  fi
}

case "${1:-status}" in
  start)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      start_napcat
      start_memory_daily
      echo "echo already running"
      exit 0
    fi
    printf -v command '%q ' "${COMMAND[@]}"
    tmux new-session -d -s "$SESSION" "$command"
    for _ in $(seq 1 60); do
      if curl -fsS --max-time 2 http://127.0.0.1:6185/ >/dev/null; then
        start_napcat
        start_memory_daily
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
    if tmux has-session -t "$NAPCAT_SESSION" 2>/dev/null; then
      tmux send-keys -t "$NAPCAT_SESSION" C-c
      sleep 2
      tmux kill-session -t "$NAPCAT_SESSION" 2>/dev/null || true
    fi
    if tmux has-session -t "$MEMORY_SESSION" 2>/dev/null; then
      tmux send-keys -t "$MEMORY_SESSION" C-c
      sleep 1
      tmux kill-session -t "$MEMORY_SESSION" 2>/dev/null || true
    fi
    stop_napcat_processes
    echo "echo and napcat stopped"
    ;;
  status)
    if tmux has-session -t "$SESSION" 2>/dev/null; then
      echo "tmux=running"
      curl -sS -o /dev/null -w 'http=%{http_code}\n' --max-time 3 \
        http://127.0.0.1:6185/ || true
    else
      echo "tmux=stopped"
    fi
    if tmux has-session -t "$NAPCAT_SESSION" 2>/dev/null; then
      echo "napcat=running"
    else
      echo "napcat=stopped"
    fi
    if tmux has-session -t "$MEMORY_SESSION" 2>/dev/null; then
      echo "memory-daily=running"
    else
      echo "memory-daily=stopped"
    fi
    ;;
  logs)
    tmux capture-pane -pt "$SESSION" -S -120
    if tmux has-session -t "$NAPCAT_SESSION" 2>/dev/null; then
      echo "--- napcat ---"
      tail -120 /data/data/com.termux/files/usr/var/lib/proot-distro/containers/ubuntu/rootfs/root/napcat.log 2>/dev/null || true
    fi
    ;;
  *)
    echo "usage: $0 {start|stop|status|logs}" >&2
    exit 2
    ;;
esac
