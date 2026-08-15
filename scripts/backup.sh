#!/usr/bin/env bash
# echo 可恢复备份：人格/记忆 + AstrBot 配置、数据库、知识库与本地插件改动
set -euo pipefail

WORKSPACE_ROOT="/home/wenbo/aaage"
BACKUP_ROOT="$WORKSPACE_ROOT/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_ROOT/echo-backup-$STAMP.tar.zst"
TMP_OUT="$OUT.tmp"
KEEP_DAYS=14
ASTRBOT_WAS_ACTIVE=0

cleanup() {
  local status=$?
  trap - EXIT
  [ -e "$TMP_OUT" ] && rm -f "$TMP_OUT"
  if [ "$ASTRBOT_WAS_ACTIVE" -eq 1 ]; then
    systemctl --user start astrbot.service || true
  fi
  exit "$status"
}
trap cleanup EXIT

umask 077
mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

# SQLite 使用 WAL 模式。短暂停止 AstrBot，避免只打包主库而漏掉 WAL 中的新数据。
if systemctl --user is-active --quiet astrbot.service; then
  ASTRBOT_WAS_ACTIVE=1
  systemctl --user stop astrbot.service
fi

WORKSPACE_FILES=(
  SOUL.md
  USER.md
  MEMORY.md
  IDENTITY.md
  AGENTS.md
  personality-log.md
  wenbo-profile.md
  memory
  assets/stickers
  astrbot/echo-persona.md
  mcp-executor/.env
  mcp-executor/workspace
)

ASTRBOT_FILES=(
  data/cmd_config.json
  data/data_v4.db
  data/data_v4.db-wal
  data/data_v4.db-shm
  data/knowledge_base
  data/config
  data/plugin_data
  data/plugins
  data/plugins.json
  data/skills.json
  data/t2i_templates
  data/mcp_server.json
)

declare -a TAR_ARGS=()
for path in "${WORKSPACE_FILES[@]}"; do
  [ -e "$WORKSPACE_ROOT/$path" ] && TAR_ARGS+=("$path")
done
for path in "${ASTRBOT_FILES[@]}"; do
  [ -e "$WORKSPACE_ROOT/astrbot/$path" ] && TAR_ARGS+=("astrbot/$path")
done

if [ "${#TAR_ARGS[@]}" -eq 0 ]; then
  echo "backup failed: no source files found" >&2
  exit 1
fi

# 社区插件仓库和自带大图可重新下载；保留运行代码、本地修改与精选表情数据。
tar --zstd -cf "$TMP_OUT" \
  -C "$WORKSPACE_ROOT" \
  --exclude='*/.git' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='astrbot/data/plugins/*/default' \
  --exclude='astrbot/data/plugins/*/data' \
  --exclude='astrbot/data/plugin_data/*/cache' \
  "${TAR_ARGS[@]}"

tar --zstd -tf "$TMP_OUT" >/dev/null
mv "$TMP_OUT" "$OUT"
chmod 600 "$OUT"

if [ "$ASTRBOT_WAS_ACTIVE" -eq 1 ]; then
  systemctl --user start astrbot.service
  systemctl --user is-active --quiet astrbot.service
  ASTRBOT_WAS_ACTIVE=0
fi

# 清理过期备份。
find "$BACKUP_ROOT" -maxdepth 1 -name 'echo-backup-*.tar.zst' -mtime "+$KEEP_DAYS" -delete

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
