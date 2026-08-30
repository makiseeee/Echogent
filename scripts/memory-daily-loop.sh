#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

PREFIX="/data/data/com.termux/files/usr"
HOME="/data/data/com.termux/files/home"
PYTHON="$PREFIX/bin/python"
SCRIPT="$HOME/echo-memory/scripts/memory-daily.sh"
EXTRACT="$HOME/echo-memory/scripts/extract_memory_candidates.py"
LOG="$HOME/echo-memory/memory-daily.log"
export PREFIX HOME PATH="$PREFIX/bin"

while true; do
  "$SCRIPT" >>"$LOG" 2>&1 || true
  # Run once per local calendar day, then sleep until the next check.
  sleep 86400
done
