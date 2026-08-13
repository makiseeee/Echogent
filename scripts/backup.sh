#!/usr/bin/env bash
# echo 全量备份：人格/记忆/技能 + AstrBot 配置/数据库/知识库/插件数据
set -euo pipefail

BACKUP_ROOT="/home/wenbo/aaage/backups"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_ROOT/echo-backup-$STAMP.tar.zst"
KEEP_DAYS=14

mkdir -p "$BACKUP_ROOT"
chmod 700 "$BACKUP_ROOT"

# 工作区：人格、记忆、技能、表情源
WORKSPACE_FILES=(
  SOUL.md
  USER.md
  MEMORY.md
  IDENTITY.md
  AGENTS.md
  personality-log.md
  wenbo-profile.md
  memory
  skills
)

# AstrBot 数据目录下的关键内容
ASTRBOT_FILES=(
  data/cmd_config.json
  data/data_v4.db
  data/knowledge_base
  data/config
  data/plugin_data
  data/mcp_server.json
)

declare -a TAR_ARGS=()
for f in "${WORKSPACE_FILES[@]}"; do
  [ -e "/home/wenbo/aaage/$f" ] && TAR_ARGS+=("/home/wenbo/aaage/$f")
done
for f in "${ASTRBOT_FILES[@]}"; do
  [ -e "/home/wenbo/aaage/astrbot/$f" ] && TAR_ARGS+=("/home/wenbo/aaage/astrbot/$f")
done

tar --zstd -cf "$OUT" "${TAR_ARGS[@]}"
chmod 600 "$OUT"

# 清理过期备份
find "$BACKUP_ROOT" -maxdepth 1 -name 'echo-backup-*.tar.zst' -mtime "+$KEEP_DAYS" -delete

echo "backup ok: $OUT ($(du -h "$OUT" | cut -f1))"
