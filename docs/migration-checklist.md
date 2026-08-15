# echo 手机迁移执行清单

目标：把 echo 的常驻聊天能力迁到手机，电脑只作为远程执行端。

原则：每一步都先验证，再进入下一步；任何涉及 QQ 登录切换、端口暴露、系统服务配置的操作都先备份。

## P0：网络与安全基线

### 当前审计结果（2026-08-14）

- AstrBot 正在运行
- Ollama 正在运行，当前模型是 `bge-m3:latest`
- NapCat Docker 正在运行
- AstrBot WebUI `6185` 监听在 `0.0.0.0`
- AstrBot OneBot 反向 WS `6199` 监听在 `0.0.0.0`
- NapCat WebUI `6099` 通过 Docker 暴露到 `0.0.0.0`
- NapCat HTTP/API `3001` 通过 Docker 暴露到 `0.0.0.0`
- `astrbot/data/mcp_server.json` 目前为空，还没有配置 MCP 执行端
- NapCat 容器环境里存在敏感登录/管理变量，迁移后必须轮换

当前结论：先做端口收敛和凭据轮换预案，再做手机迁移。

对应操作文档：

- `docs/runbook-port-hardening.md`

### P0 执行结果（2026-08-14）

- [x] 新备份：`backups/echo-backup-20260814-195730.tar.zst`
- [x] 备份脚本补齐 SQLite/WAL 一致性、本地插件改动与精选表情
- [x] AstrBot WebUI 收紧为 `127.0.0.1:6185`
- [x] NapCat WebUI 收紧为 `127.0.0.1:6099`
- [x] 废弃的旧 OneBot WebSocket `3001` 不再发布到宿主机
- [x] AstrBot OneBot 反向 WS 收紧为 Docker 网桥 `172.17.0.1:6199`
- [x] AstrBot、NapCat 与 QQ 反向 WS 均已恢复运行
- [ ] 迁移窗口内轮换 WebUI、OneBot、MCP 与快速登录相关凭据

当前下一步：进入 P1，先实现电脑端最小 MCP Server。

### 0.1 设备命名

- 手机 tailnet 名称：`echo-phone`
- 电脑 tailnet 名称：`echo-school`
- 电脑 MCP 监听地址：只绑定 tailnet IP 或 `127.0.0.1` 经 Tailscale 转发
- AstrBot/NapCat 管理端口：默认不对公网或局域网暴露

验证：

```bash
tailscale status
tailscale ping echo-school
tailscale ping echo-phone
```

### 0.2 端口策略

电脑当前需要收紧或明确用途的端口：

- `6099`：NapCat WebUI
- `3001`：NapCat HTTP/API
- `6199`：AstrBot OneBot 反向 WS
- `6185`：AstrBot WebUI

目标状态：

- WebUI 只允许本机或 tailnet 访问
- OneBot 反向 WS 只给 NapCat 连
- MCP Server 只允许手机 tailnet 节点访问

电脑端过渡期建议：

- AstrBot WebUI：`127.0.0.1:6185`
- AstrBot OneBot 反向 WS：若 NapCat 仍在 Docker，先保持宿主机可达；确认 Docker 网络后再收紧
- NapCat WebUI：`127.0.0.1:6099`
- NapCat HTTP/API：不用就关闭；要用则 `127.0.0.1:3001`

验证：

```bash
ss -lntp
tailscale status
```

本机端口审计：

```bash
ss -lntp
docker ps --filter name=napcat --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
```

### 0.3 凭据轮换

迁移后必须更换：

- AstrBot WebUI 密码
- NapCat WebUI token
- OneBot reverse websocket token
- MCP Bearer token
- NapCat 快速登录/管理相关环境变量

注意：`astrbot/data/cmd_config.json`、`astrbot/data/mcp_server.json`、NapCat 配置都视为私密文件。

## P0 下一步操作

### A. 先备份当前可运行状态

```bash
bash scripts/backup.sh
```

验收：

- `backups/echo-backup-*.tar.zst` 新增一份备份

### B. 收紧 AstrBot WebUI

目标：

- `dashboard.host` 从 `0.0.0.0` 改为 `127.0.0.1`
- 保持 `dashboard.port=6185`

操作后需要重启 AstrBot。

验收：

```bash
ss -lntp | grep 6185
```

应看到 `127.0.0.1:6185`，而不是 `0.0.0.0:6185`。

### C. 收紧 NapCat Docker 端口

目标：

- `6099` 改为只绑定 `127.0.0.1`
- `3001` 若不使用则不发布；若继续使用则只绑定 `127.0.0.1`

这一步通常需要重建或重启容器，操作前必须确认当前容器启动命令或 compose 文件。

验收：

```bash
docker ps --filter name=napcat --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -lntp | grep -E '6099|3001'
```

应看到 `127.0.0.1:6099`，不应看到 `0.0.0.0:6099`。

### D. 再决定 OneBot 反向 WS 是否收紧

如果 NapCat 在宿主机外的 Docker 网络里连接 AstrBot，`6199` 不能贸然改成 `127.0.0.1`，否则 QQ 消息可能断。

候选方案：

- 让 NapCat 使用 host 网络或明确宿主机网关地址
- AstrBot 仅绑定 Docker 网桥可达地址
- 保持 `6199` 暂时开放，但依赖强 token，并只在迁移窗口内保留

## P1：电脑端 MCP 最小可用

先在电脑上跑一个最小 MCP Server，只暴露低风险工具。

第一批工具：

- `health_check`：返回执行端在线状态
- `run_python`：只在临时目录运行，默认超时 10 秒
- `read_file`：限制在允许目录内

暂不开放：

- 任意 `run_shell`
- 任意 `write_file`
- 系统控制、开关机、改网络配置

验收标准：

- AstrBot 能看到 MCP 工具列表
- QQ 中请求执行一个简单 Python 表达式能返回结果
- 电脑 MCP 停止时，echo 能明确说执行端离线

回滚：

- 删除或清空 `astrbot/data/mcp_server.json` 的新增 server
- 重启 AstrBot

### P1 执行结果（2026-08-14）

- [x] 部署 `echo-executor`，仅监听 `127.0.0.1:8765/mcp`
- [x] Bearer Token 已生成到权限 600 的 `mcp-executor/.env`
- [x] 未授权请求返回 HTTP 401
- [x] 暴露工具仅为 `health_check`、`run_python`、`read_file`
- [x] `run_python` 使用 namespace、AST 白名单、资源与输出限制
- [x] `read_file` 仅可读取 `mcp-executor/workspace`
- [x] AstrBot 裸机执行已关闭：`computer_use_runtime=none`
- [x] coder 已移除 shell、宿主 Python 和文件写入工具
- [x] AstrBot 日志确认三个 MCP 工具连接成功
- [x] systemd 用户服务已启用，linger=yes，端口只监听本机
- [x] 停止 MCP 时 AstrBot 保持在线，恢复后端点正常返回 401
- [x] 7 项沙盒回归测试通过
- [ ] 通过 QQ 实测一次复杂计算委派

当前下一步：先完成 QQ 实聊验收，再进入 P2 手机端试运行。

## P2：手机端 AstrBot/NapCat 试运行

先不切 QQ 登录，只把手机环境跑起来。

前置条件：

- 手机 4GB+ 内存优先
- ZeroTermux/proot Ubuntu 可用
- Python、uv、Node/npm 可用
- Tailscale 可用

先迁移：

- `SOUL.md`
- `USER.md`
- `MEMORY.md`
- `IDENTITY.md`
- `memory/`
- `assets/stickers/`
- `astrbot/data/config/`
- `astrbot/data/plugin_data/`
- `astrbot/data/plugins/`

谨慎迁移：

- `astrbot/data/cmd_config.json`：迁后必须改端口、密码、token、embedding 模型
- `astrbot/data/data_v4.db`：停 AstrBot 后再拷贝

不直接迁移：

- `astrbot/data/knowledge_base/`：bge-m3 与 bge-small-zh 维度不同，手机端重建
- `astrbot/data/*.db-wal`
- `astrbot/data/*.db-shm`

验收标准：

- 手机 AstrBot WebUI 可本机访问
- 手机 NapCat 可启动到登录页
- 手机 AstrBot 不依赖电脑也能启动

### P2 当前进度（2026-08-15）

- [x] 确认手机为 GIONEE GD032313，ARM64、Android 11、4GB+64GB
- [x] 安装 Termux 0.118.3、Termux:Boot 0.8.1、tmux 与 proot-distro
- [x] 通过 `dockerproxy.net` 安装 Ubuntu 24.04 ARM64
- [x] Ubuntu 切换清华源并安装 Python 3.12、uv、AstrBot 4.27.2
- [x] 手机 AstrBot WebUI 仅监听 `127.0.0.1:6185`
- [x] 手机端关闭裸机执行，并仅启用 WebChat
- [x] DeepSeek 聊天模型加载成功，本地 Ollama embedding 已禁用
- [x] 迁移 echo-tools、self_evolution、meme_manager_lite 与插件数据
- [x] 三套插件加载成功，精选表情数据已识别
- [x] 配置 tmux 常驻管理、Termux:Boot、自启脚本与后台白名单
- [x] 手动运行开机脚本后 AstrBot 自动恢复，WebUI 返回 HTTP 200
- [x] 实际重启手机验证 Termux:Boot，重启后 `tmux=running`、`http=200`
- [ ] 手机 WebChat 实聊验证 DeepSeek、人格、记忆与表情
- [x] 使用 ZeroTier 代替 Tailscale，手机经私网成功连接电脑 MCP（1/1 successful）
- [ ] 评估 ARM64 手机上的 NapCat 可行性，暂不切 QQ 登录

当前可通过 USB 调试访问手机 WebUI：

```bash
adb forward tcp:16185 tcp:6185
```

然后在电脑打开 `http://127.0.0.1:16185`。

## P3：QQ 登录切换

操作前：

```bash
bash agent-status.sh
systemctl --user stop astrbot.service
docker stop napcat
```

切换原则：

- 同一机器人 QQ 号只保留一个 NapCat 登录端在线
- 手机登录成功后，先用 QQ 私聊测试普通回复
- 再测试表情、记忆、搜索

回滚：

- 停手机 NapCat/AstrBot
- 恢复电脑 NapCat
- 启动电脑 AstrBot

## P4：远程执行联调

手机 AstrBot 通过 ZeroTier 私网访问电脑 MCP。

验收标准：

- 电脑在线：执行工具可用
- 电脑离线：聊天、表情、记忆不受影响
- 执行请求超时后有清楚提示，不抛原始堆栈

## P5：稳定性

连续运行 48 小时观察：

- 手机温度
- 电池策略
- 断网重连
- QQ 是否掉线
- AstrBot 日志是否持续报错
- 备份是否成功

手机端状态脚本需要单独做，不复用当前 Docker/systemd 版本。
