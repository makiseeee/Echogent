#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TODAY="$(date +%F)"
DAILY="$ROOT/memory/$TODAY.md"

python3 "$ROOT/scripts/memory_manager.py" expire >/dev/null

if [[ -s "$DAILY" ]]; then
  summary="$(sed -n '1,80p' "$DAILY")"
else
  summary="今天尚无每日记录；保留现有任务，等待新对话更新。"
fi

python3 "$ROOT/scripts/memory_manager.py" current "$summary" >/dev/null
python3 "$ROOT/scripts/extract_memory_candidates.py" "$DAILY" >/dev/null 2>&1 || true
printf 'updated %s from %s\n' "$ROOT/memory/current.md" "$DAILY"
