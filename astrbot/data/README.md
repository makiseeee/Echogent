# astrbot/data/ - 运行数据（不入库）

由 AstrBot 运行生成，包含：

- `cmd_config.json`：主配置（含 API key、WebUI 密码哈希）——私密
- `data_v4.db`：数据库（人设、定时任务等）
- `knowledge_base/`：知识库索引（RAG）
- `plugins/`：插件（部分来自社区，可用 `astrbot plug install` 或 git clone 安装）
- `plugin_data/`：表情包、self_evolution 记忆
- `temp/`：临时文件（含 `echo-scripts/`，每日 04:00 自动清理）

全新环境：先 `astrbot init` 生成该目录，再参考顶层 README 完成配置。
