# Echogent

基于 AstrBot 的个人 QQ Agent。手机负责常驻聊天、记忆和知识库，电脑按需提供受限代码执行、Obsidian 访问与 Ollama Embedding。

## 当前架构

```text
QQ
  -> 手机 NapCat / OneBot v11
  -> 手机 AstrBot
       -> Hajimi Responses API / deepseek-v4-flash：主对话模型
       -> self_evolution：记忆、画像、每日总结
       -> echo-tools：搜索、网页抓取、计算器
       -> kaomoji：颜文字反应
       -> ZeroTier -> 电脑 MCP：受限 Python、只读文件、Obsidian
       -> ZeroTier -> 电脑 Ollama bge-m3：知识库向量
```

手机是运行数据、记忆和知识库的主副本。Agent 会在每次模型请求前探测电脑执行端，并临时告知模型当前可用能力。电脑关闭时，QQ 对话和已有记忆仍可用；远程执行、Obsidian 和新增知识向量会暂时不可用，失败的每日总结会定时补录。

## 文档入口

- [文档索引](docs/README.md)
- [当前架构](docs/architecture.md)
- [能力与边界](docs/capabilities.md)
- [日常运维](docs/operations.md)
- [网络与安全](docs/security.md)
- [剩余工作](docs/roadmap.md)
- [历史迁移记录](docs/archive/README.md)

## 常用命令

```bash
# 远程登录手机 Termux
ssh phone-echo

# 查看手机服务
ssh -o RequestTTY=no phone-echo '~/echo-service status'

# 进入手机 Ubuntu
ssh phone-echo
proot-distro login ubuntu

# 查看电脑执行端
systemctl --user status echo-mcp.service
curl http://127.0.0.1:8765/status

# 查看电脑 Embedding 服务
systemctl --user status ollama.service
```

## 目录

- `scripts/`：手机部署、配置与电脑服务脚本
- `systemd/`：电脑端用户服务模板
- `mcp-executor/`：受限 MCP 执行端
- `patches/`：本地插件定制补丁
- `docs/`：当前文档与历史记录
- `astrbot/`：电脑侧迁移源和恢复副本，不是当前在线主实例
- `SOUL.md`、`USER.md`、`MEMORY.md`、`memory/`：人格与文本记忆源

私密配置、Token、QQ 登录数据、数据库和手机运行数据不得提交到 GitHub。
