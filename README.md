# echo 

## 架构

```text
手机 QQ ──→ NapCat(Docker, OneBot v11) ──→ AstrBot(反向 WS 6199) ──→ DeepSeek v4-flash
                                              │
                                              ├─ Ollama(bge-m3) 本地嵌入 → 知识库 RAG
                                              ├─ self_evolution：记忆/画像/好感度/每日16:00总结
                                              ├─ meme_manager_lite：表情包（49张精选，发前压缩250px）
                                              └─ echo-tools：Bing 搜索 / 网页抓取 / 安全计算器
```

## 目录结构

- `astrbot/` —— AstrBot 工作目录（`data/cmd_config.json` 主配置、`data/plugins/` 插件、`data/knowledge_base/` 知识库索引、`data/plugin_data/` 表情与记忆数据）
- `SOUL.md` / `USER.md` / `MEMORY.md` / `IDENTITY.md` / `personality-log.md` —— 人设与记忆体系
- `memory/` —— 每日日志
- `wenbo-profile.md` —— 用户简历（私密，仅知识库按需引用）
- `assets/stickers/` —— 表情包源图（49 张）
- `scripts/backup.sh` —— 每日备份脚本
- `tools/napcat-setup.sh` —— NapCat 安装脚本（参考）
- `backups/` —— 备份产物（自动保留 14 天）

## 运维命令

```bash
# 状态
bash agent-status.sh

# AstrBot
systemctl --user status astrbot.service
systemctl --user restart astrbot.service
journalctl --user -u astrbot.service -f

# Ollama（本地嵌入）
systemctl --user status ollama.service

# 定时器
systemctl --user list-timers | grep echo
```

WebUI：http://127.0.0.1:6185（账号密码见本地配置 `astrbot/data/cmd_config.json`，建议改密）

## 备份与恢复

- 每日 03:30 自动备份到 `backups/echo-backup-*.tar.zst`（保留 14 天）
- 恢复：先 `systemctl --user stop astrbot.service`，再解包按原路径放回

## 记忆机制

- **echo-kb 知识库**：静态资料（简历、偏好），`astr_kb_search` 按需检索
- **self_evolution 记忆库**：动态记忆（会话总结、画像、情绪），每日 16:00 自动写入
- 临时脚本统一放 `astrbot/data/temp/echo-scripts/`，每日 04:00 自动清理
