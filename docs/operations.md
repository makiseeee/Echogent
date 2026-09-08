# 日常运维与排障手册

本文档提供 **Echogent (Echo 7.0)** 在 Xiaomi MIX 2 硬件底座与 Windows PC 宿主环境下的标准运维作业、平滑热更与常见故障处置指南。

---

## 1. 远程连接标准 (USB-First 准则)

手机与工位 PC 保持物理 USB 常驻连接。**所有运维操作必须绝对优先走 USB ADB 高速转发通道**，以获得超低延迟、零丢包和高速文件传输体验。

### 1.1 USB 快速登录
在 Windows PowerShell 7 (`pwsh`) 或 WSL 中执行：

```bash
# 1. 确认已开启 ADB 端口转发 (电脑端执行)
adb.exe forward tcp:8022 tcp:8022

# 2. 通过 SSH 直连手机 Termux (127.0.0.1:8022)
ssh phone-usb

# 3. 登录 Ubuntu PRoot 容器系统
proot-distro login ubuntu
```

> [!NOTE]
> `~/.ssh/config` 中 `phone-usb` 配置指向 `HostName 127.0.0.1, Port 8022, User u0_a145`。
> 仅在外出工位断开 USB 时，方降级使用 ZeroTier 虚拟网 IP 通道 (`ssh phone-echo`)。

---

## 2. 服务管理与平滑重载

### 2.1 查看服务健康度
在手机 Termux 环境中执行：

```bash
echo-service status
```

**健康基线输出预期**：
```text
mihomo=running (port 7890)      # 科学网络代理 (保障 LLM 访问)
echo_agent=running              # AstrBot 主会话进程
astrbot_http=200                # AstrBot 核心 Web 接口就绪
hud_server=running (port 8099)  # 离线 Live2D 桌面伴侣屏就绪
light_sentry=running            # 光感自动熄屏守护进程
napcat=running                  # LinuxQQ 协议网关正常
```

### 2.2 轻量重载规范 (严禁无故全量重启)
> [!CAUTION]
> **严禁轻易执行 `echo-service stop` 或 `echo-service restart`！**
> 重新拉起 LinuxQQ / NapCat 会触发复杂的 Chromium 运行时加载，导致骁龙 835 CPU 瞬间飙升至 100%（系统 Load Average 飙至 8+），极易引发系统 OOM 崩溃。

针对不同的修改场景，请严格采用以下**轻量级平滑重载**：

1. **仅修改人设 (`SOUL.md` / `RELATIONSHIP.md`) 或插件业务逻辑**：
   - 优先通过 AstrBot WebUI (`http://127.0.0.1:6185`) 仪表盘点击“重新加载插件”；
   - 或仅销毁重启 `echo` tmux 会话（保持 NapCat 与 QQ 登录态完全不动）：
     ```bash
     tmux kill-session -t echo
     # echo-service 守护进程会在 5 秒内无感拉起新的 AstrBot 实例
     ```
2. **解决端口绑定失败或异常死锁**：
   - PRoot 内部进程在外部均表现为 `/libexec/proot/loader`，严禁使用盲目的 `pkill -f astrbot`；
   - 若 AstrBot 提示 `port 6185 already in use` 或无法绑定，检查并清除残留锁文件：
     ```bash
     rm -f /opt/echo/astrbot.lock
     ```

---

## 3. 电脑端 PC Agent 管理

PC Agent 负责追踪前台活动窗口并提供伴侣感知数据：

```powershell
# 1. 启动 PC Agent (支持系统托盘)
.\echo_pc_agent\run.bat

# 2. 静默后台启动 (无黑框)
wscript.exe .\echo_pc_agent\run.vbs

# 3. 检查 PC Agent 本地公开状态
curl.exe -s http://127.0.0.1:8765/status
```

**预期返回结构**：
```json
{
  "online": true,
  "active_window": "Visual Studio Code - aaage",
  "process_name": "Code.exe",
  "idle_seconds": 12,
  "humanized_activity": "写代码"
}
```

---

## 4. Web 仪表盘与可视化访问

所有管理端口默认仅监听本地回环 `127.0.0.1`，电脑端通过 ADB 端口映射访问：

```powershell
# 映射 AstrBot 仪表盘 (6185)、NapCat 控制台 (6099) 与 Live2D HUD (8099)
adb.exe forward tcp:6185 tcp:6185
adb.exe forward tcp:6099 tcp:6099
adb.exe forward tcp:8099 tcp:8099
```

- **AstrBot Web 控制台**：`http://127.0.0.1:6185/`
- **NapCat QQ 配置控制台**：`http://127.0.0.1:6099/webui`
- **Live2D 桌面伴侣仪表盘**：`http://127.0.0.1:8099/dashboard.html`

---

## 5. 常见故障诊断与恢复

### 5.1 QQ 私聊不回复
1. 执行 `ssh phone-usb "echo-service status"` 检查 `napcat` 与 `echo_agent` 状态；
2. 检查 QQ 掉线日志：`ssh phone-usb "tmux capture-pane -pt napcat -S -50"`；
3. 若 QQ 被风控踢出登录，打开 `http://127.0.0.1:6099/webui` 重新扫码登录。

### 5.2 Obsidian 日记写入未生效或 Git 冲突
1. 检查手机本地日记仓库状态：
   ```bash
   ssh phone-usb "proot-distro login ubuntu -- git -C /opt/echo/data/obsidian-vault status"
   ```
2. 若存在未决的 rebase，执行重置中断：
   ```bash
   ssh phone-usb "proot-distro login ubuntu -- git -C /opt/echo/data/obsidian-vault rebase --abort"
   ```
3. 触发一次手动 Pull 强制对齐：
   ```bash
   ssh phone-usb "proot-distro login ubuntu -- git -C /opt/echo/data/obsidian-vault pull --rebase"
   ```

### 5.3 伴侣屏关灯后未自动熄屏
1. 确认 Termux API 传感器扩展权限已激活：`termux-sensor -l`；
2. 检查光敏守护进程日志：`cat ~/.echo/light.log`；
3. 测试实时光照数值：`termux-sensor -s "light" -n 1`（低于 3.0 Lux 自动进入熄屏模式）。
