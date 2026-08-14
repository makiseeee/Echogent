# echo ✨ 手机端部署架构设计

## 目标

- **手机（家里，7×24 充电联网）**：运行 echo 本体（AstrBot + NapCat + 记忆/知识库）
- **电脑（学校）**：作为"执行端"，提供沙盒 / 跑代码 / 控制电脑的能力
- 人在学校用 QQ 和 echo 交互；echo 需要执行时，远程调用学校电脑

## 拓扑

```text
[家里]                              [学校]
手机(安卓 · ZeroTermux + proot Ubuntu)   电脑(Windows/WSL)
├─ NapCat(QQ 登录端)                ├─ MCP Server（执行服务）
├─ AstrBot(echo 本体)                │   ├─ run_python 沙盒
│   ├─ DeepSeek(云端 API)            │   ├─ run_shell
│   ├─ 记忆 / 画像 / 知识库           │   └─ 文件读写 / 系统控制(可选)
│   └─ 插件 / 表情包                  └─ Tailscale 节点
└─ Tailscale 节点 ◄═══ 加密隧道 ═══► Tailscale 网络
```

消息流：wenbo 发 QQ → 腾讯 → 家里 NapCat → 家里 AstrBot →（需要执行时）经 Tailscale
调学校电脑 MCP Server → 结果回传 → echo 傲娇回复。

## 关键决策

### 1. QQ 登录端 = 手机（推荐）

- 手机常开，QQ 在线稳定；电脑关机/断网不影响聊天
- 现状电脑端 NapCat 停用（同一机器人账号不能同时在线）
- 方案成熟：`NapNeko/NapCat-Termux`（ZeroTermux + bookworm + linuxqq，官方项目）
- 风险：手机发热/电池 → 需要"永不休眠 + 充电策略"

### 2. 网络 = Tailscale（推荐）

- 免费、无需公网 IP、端到端加密；学校 NAT 也能通（DERP 中继兜底）
- 手机 AstrBot 通过 tailnet 私有 IP 连电脑 MCP Server
- 备选：frp（需要一台有公网 IP 的服务器，暴露端口有风险）

### 3. 电脑执行端 = MCP Server

- AstrBot 原生支持 MCP（sse / streamable_http / stdio），配置 `data/mcp_server.json`
- 现成方案：`ssh-mcp`（基于 SSH 远程执行，最快落地）
- 更定制：自写一个 MCP Server（fastmcp / 官方 SDK），暴露
  `run_python` / `run_shell` / `read_file` / `write_file`（限目录 + token 鉴权）
- 安全：只监听 tailnet 地址 + Bearer token；代码执行可再套 docker 沙盒

### 4. 手机端嵌入模型

- bge-m3（1.2GB）在旧手机上吃力 → 换 **bge-small-zh**（约 90MB）重建 echo-kb
- 或第一阶段先不迁知识库，用 self_evolution 记忆 + 聊天兜底

### 5. 降级设计

- 电脑离线时：echo 正常聊天 / 记忆 / 表情 / 搜索，仅执行类工具不可用
- echo 应当能感知执行端离线并告诉用户，而不是报错

## 数据迁移

- `astrbot/data/` 整体拷贝到手机（config 调整：执行类工具改为远程 MCP）
- 知识库：手机用 bge-small-zh 重建（bge-m3 向量维度不同，不能直接复用 kb.db）
- 备份：手机端每日备份到本机 + 定期拉回电脑

## 分阶段落地

| 阶段 | 内容 | 验证标准 |
|---|---|---|
| P1 | 电脑端 MCP Server（先在 WSL 做好） | AstrBot→MCP 远程执行跑通 |
| P2 | 手机 Termux 部署（proot Ubuntu + AstrBot + NapCat），数据迁移，QQ 登录切换 | 手机端独立可聊 |
| P3 | Tailscale 组网 + 联调 | 学校电脑开机时远程执行可用、离线降级正常 |
| P4 | 稳定性：自启、监控、备份、发热控制 | 连续运行 48h 无异常 |

## 风险与待确认

- QQ 登录迁移：手机扫码登录机器人号，原电脑 NapCat 停用
- Tailscale 在学校网络的可达性（DERP 中继是否通，需实测）
- 手机内存：建议 4GB+；2GB 跑 proot Ubuntu + AstrBot + NapCat 会比较吃力
- 执行能力仅在学校电脑开机时可用（可加"电脑开机自动连 tailnet + 起 MCP"）
