# 日常运维

## 远程登录

WSL 的 `~/.ssh/config` 已配置：

```sshconfig
Host phone-echo
    HostName 10.144.13.0
    User u0_a200
    Port 8022
    IdentityFile ~/.ssh/echo-phone
```

连接 Termux：

```bash
ssh phone-echo
```

进入 Ubuntu：

```bash
proot-distro login ubuntu
```

如果 SSH 连接失败，先确认手机 ZeroTier 网络 `e3918db483ca8634` 已启用。USB 仍可作为最后的 ADB 恢复通道。

## 手机服务

在 Termux 中：

```bash
~/echo-service start
~/echo-service stop
~/echo-service status
~/echo-service logs
tmux list-sessions
```

正常状态：

```text
tmux=running
http=200
napcat=running
```

tmux 会话：

- `echo`：AstrBot
- `napcat`：Linux QQ 与 NapCat

## 启动恢复

首选流程：

1. 手机开机后首次解锁
2. 等待 Termux:Boot 尝试启动
3. 若 QQ 两分钟内不回复，打开一次 Termux
4. 运行 `~/echo-service status`

这台手机的系统偶尔不投递开机广播，因此“打开 Termux 自动恢复”是当前可靠兜底。

## 电脑服务

```bash
systemctl --user status echo-mcp.service
systemctl --user restart echo-mcp.service
journalctl --user -u echo-mcp.service -f

systemctl --user status ollama.service
systemctl --user restart ollama.service
journalctl --user -u ollama.service -f
```

检查执行端对手机公开的状态：

```bash
curl -s http://127.0.0.1:8765/status
```

QQ 中发送 `/电脑状态` 会绕过 60 秒缓存立即探测。普通对话时插件会把在线状态和能力列表作为临时上下文注入模型，不写入聊天历史。

端口检查：

```bash
ss -lntp | grep -E '8765|11434'
```

预期：

- MCP：`0.0.0.0:8765`，Bearer Token 鉴权，Windows 防火墙仅允许手机 ZeroTier IP
- Ollama：`10.144.232.236:11434`，仅绑定电脑 ZeroTier 地址

## WebUI

手机 AstrBot WebUI 只监听 `127.0.0.1:6185`，NapCat WebUI 只监听 `127.0.0.1:6099`。

临时通过 USB 转发：

```bash
adb forward tcp:16185 tcp:6185
adb forward tcp:16099 tcp:6099
```

然后访问：

- AstrBot：`http://127.0.0.1:16185`
- NapCat：`http://127.0.0.1:16099`

Token 和密码只从本地私密配置读取，不写入文档。

## 常见故障

### QQ 不回复

```bash
ssh -o RequestTTY=no phone-echo '~/echo-service status'
ssh -o RequestTTY=no phone-echo '~/echo-service logs'
```

依次确认 `http=200`、`napcat=running`，以及日志包含 OneBot 适配器已连接。

### SSH 不通

1. 检查手机 ZeroTier 是否启用
2. 从电脑 `ping 10.144.13.0`
3. 必要时用 USB 打开 Termux 并运行 `sshd`

### 远程执行不可用

```bash
systemctl --user is-active echo-mcp.service
curl -i --max-time 3 http://127.0.0.1:8765/mcp
```

无 Token 返回 HTTP 401 是正常状态。

`/status` 是无敏感数据的只读探针；正常返回 `online: true` 和能力列表。若 QQ 显示电脑离线，依次检查 WSL、`echo-mcp.service`、ZeroTier 和 Windows 防火墙。

### 新记忆未进入知识库

确认电脑 Ollama、两端 ZeroTier 在线。失败总结保存在手机插件数据目录的 `pending_kb_uploads.json`，定时器每 30 分钟重试，不要手工删除该文件。

## 备份

电脑的 `scripts/backup.sh` 只备份电脑工作区和迁移副本，不能替代手机在线数据备份。手机主数据库的自动一致性备份仍在待办列表中。
