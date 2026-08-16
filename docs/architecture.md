# 当前架构

## 角色分工

### 手机：常驻主机

- 设备：GIONEE GD032313，Android 11，ARM64，4GB RAM，64GB 存储
- Termux + Ubuntu 24.04 proot
- AstrBot 4.27.2：`/opt/echo`
- Linux QQ + NapCat 4.18.19
- 记忆、插件数据库、知识库数据库和向量索引的主副本
- ZeroTier 节点：`10.144.13.0`

### 电脑：按需计算端

- WSL 中运行 `echo-mcp.service`
- MCP 只开放健康检查、受限 Python 和白名单目录只读
- Ollama 使用 `bge-m3` 生成 1024 维向量
- ZeroTier 节点：`10.144.232.236`
- 旧 NapCat Docker 容器已停止，不再登录机器人 QQ

## 消息流

```text
用户 QQ
  -> 腾讯 QQ
  -> 手机 Linux QQ / NapCat
  -> OneBot 反向 WebSocket 127.0.0.1:6199
  -> 手机 AstrBot
  -> DeepSeek 生成回复
  -> NapCat 发回 QQ
```

需要额外能力时，AstrBot 经 ZeroTier 调用电脑：

```text
远程执行 -> 10.144.232.236:8765/mcp -> echo-executor
Embedding -> 10.144.232.236:11434 -> Ollama bge-m3
```

## 数据归属

| 数据 | 主副本 | 说明 |
|---|---|---|
| AstrBot 运行配置 | 手机 | `/opt/echo/data` |
| QQ/NapCat 登录数据 | 手机 | Ubuntu 中的 NapCat/QQ 目录 |
| self_evolution 动态记忆 | 手机 | 插件 SQLite 数据库 |
| AstrBot 知识库与 FAISS 索引 | 手机 | `/opt/echo/data/knowledge_base` |
| 人格和文本记忆源 | Git 工作区 | `SOUL.md`、`USER.md`、`MEMORY.md`、`memory/` |
| MCP 只读工作区 | 电脑 | `mcp-executor/workspace` |
| Ollama 模型 | 电脑 | `bge-m3` |

电脑仓库中的 `astrbot/data` 是迁移源和恢复参考，不应视为在线数据库。

## 降级行为

- 电脑关机：QQ 对话、DeepSeek、搜索和已有记忆继续工作
- MCP 离线：远程执行工具不可用，不影响普通聊天
- Ollama 离线：已有知识库仍可检索；新总结无法生成向量时进入待处理队列
- ZeroTier 离线：手机仍可 QQ 对话，但不能访问电脑 MCP/Ollama，也不能通过 SSH 维护
- Termux:Boot 未触发：解锁后打开 Termux，交互启动脚本会恢复 SSH、AstrBot 和 NapCat

## 当前边界

- 不开放任意 Shell、任意文件写入或桌面程序启动
- 图片表情包暂时停用，LLM 贴纸标签输出为颜文字
- 手机供电自动化、ZeroTier 开机恢复和完整手机备份仍待完善
