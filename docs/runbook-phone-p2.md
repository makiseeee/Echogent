# 手机端 P2 运行手册

当前设备：GIONEE GD032313，Android 11，ARM64，4GB 内存，64GB 存储。

## 当前架构

- Android：Termux 与 Termux:Boot
- Linux 用户空间：Ubuntu 24.04 ARM64（proot-distro）
- AstrBot：4.27.2，安装在 `/opt/echo-astrbot`
- AstrBot 数据：`/opt/echo/data`
- WebUI：仅监听手机本机 `127.0.0.1:6185`
- 常驻方式：Termux tmux 会话 `echo`

## 手机 Termux 管理命令

```bash
~/echo-service start
~/echo-service stop
~/echo-service status
~/echo-service logs
```

## USB 调试访问 WebUI

Windows 上执行：

```powershell
adb forward tcp:16185 tcp:6185
```

电脑浏览器访问 `http://127.0.0.1:16185`。

## 开机自启

Termux:Boot 执行：

```text
~/.termux/boot/start-echo
```

脚本会申请 wakelock，再通过 `~/echo-service start` 启动 AstrBot。

## 安全边界

- 手机 WebUI 不监听局域网地址
- 手机不启用 OneBot/QQ 平台
- 手机 `computer_use_runtime=none`
- 手机不使用电脑的 Ollama embedding
- 电脑 MCP 已通过 ZeroTier 向手机开放，仅允许手机私网地址并使用 Bearer token

## 剩余验收

1. WebChat 实测人格、DeepSeek、记忆、表情和远程执行
2. 评估 ARM64 手机上的 QQ 登录端方案
3. 最后迁移 QQ 登录并进行 48 小时稳定性观察
