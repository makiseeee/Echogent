#!/usr/bin/env bash
set -euo pipefail

VAULT="${1:-/mnt/d/wenboo}"
REMOTE="${2:-https://gitee.com/Weeenbo/obsidian-g-i-t.git}"

if [[ ! -d "$VAULT/.git" ]]; then
  echo "Vault git directory not found: $VAULT" >&2
  exit 1
fi
git -C "$VAULT" remote get-url origin >/dev/null 2>&1 || git -C "$VAULT" remote add origin "$REMOTE"
git -C "$VAULT" remote set-url origin "$REMOTE"
git -C "$VAULT" branch -M main
git -C "$VAULT" push -u origin main
echo "Gitee initial push completed: $VAULT"
