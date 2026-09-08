<div align="center">

# Echogent (Echo 7.0)

**Private AI desktop companion agent running 24/7 on a Xiaomi MIX 2**

*QQ Chat · Obsidian Vault · Live2D HUD · Proactive Scheduling · Desktop Awareness*

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Android%20%7C%20Windows-green.svg)](#运行环境与角色分工)
[![AstrBot](https://img.shields.io/badge/Powered%20by-AstrBot%204.27+-orange.svg)](https://github.com/Soulter/AstrBot)

</div>

---

专为 **wenbo** 设计的个人私有智能桌面伴侣与伙伴 Agent。系统常驻运行于 **Xiaomi MIX 2 (Snapdragon 835, 6GB RAM)** 私有硬件底座上，无缝联动 QQ 私聊即时通讯、Obsidian 知识库与任务仓库、PC 桌面活动感知、100% 离线 Live2D 桌面 HUD 以及自适应主动日程调度系统。

## ✨ Highlights

- 🤖 **傲娇女友人设** — 不是冷冰冰的助手，而是有性格、有记忆、会吃醋的 AI 伴侣
- 📱 **手机 24/7 常驻** — 骁龙 835 低功耗长运行，宿舍桌面专属智能硬件底座
- 🎭 **Live2D 离线伴侣屏** — 桃濑日和 Cubism 4 模型，触控交互 + 情绪系统 + 对白气泡
- 📓 **Obsidian 双向同步** — 日记、任务、笔记实时闭环，两阶段提交防误操作
- 👁️ **桌面活动感知** — PC 窗口探针 → 自然语义映射（"写代码"、"摸鱼"），零截图隐私保护
- 🌙 **心流决策引擎** — 结合时间/光照/活跃度，自主判断主动问候或静默陪伴
- 💰 **多模型热切 + 精确计费** — DeepSeek / Claude / Qwen 无缝切换，CNY/USD 双币种账本

---

## 🏗️ Architecture

```text
[PC Windows 11 / WSL]                             [Xiaomi MIX 2 (Termux + PRoot Ubuntu)]
+-----------------------------+                  +----------------------------------------------+
| Echo PC Agent (port 8765)   |                  | AstrBot 4.27+ (port 6185)                   |
|  - Active Window Tracker    |  HTTP Activity   |  - Core Plugins:                             |
|  - System Tray Daemon       | ---------------->|     * echo-tools (解耦分层架构)              |
|                             |                  |     * astrbot_plugin_self_evolution (长程记忆)|
| Obsidian Vault (PC)         |                  |     * astrbot_plugin_meme_manager_lite       |
|  - 2. Areas / 日记 / Tasks  |  Git Sync (Gitee)|  - NAPCat / LinuxQQ (OneBot v11 port 6199)   |
|                             | <=============>  |  - Proactive Scheduler (晨报 08:00/晚报 23:20)|
+-----------------------------+                  +----------------------------------------------+
              ^                                                         |
              | USB / ADB Forward (127.0.0.1:8022)                      v
              +----------------------------------------> [硬件级守护与离线伴侣 (MIX 2)]
                                                         - Live2D HUD Server (port 8099, 纯离线)
                                                         - Face Sentry (人脸感知哨兵, 30ms 局部唤醒)
                                                         - Light Sensor Daemon (光感关灯自动熄屏)
```

### 运行环境与角色分工
- **手机常驻端 (Xiaomi MIX 2)**：
  - 高通骁龙 835，6GB LPDDR4x，全贴合屏幕，作为常驻桌面伴侣硬件底座。
  - Termux + Ubuntu 24.04 PRoot 环境 (`/opt/echo`)，承载 AstrBot 核心、NapCat QQ 协议端、Live2D 伴侣屏服务及人脸/光感感知守护。
  - 拥有长程记忆数据库 (`data_v4.db`)、Token 计费数据库 (`echo-tools-token-usage.db`) 与本地 Obsidian Vault 镜像副本。
- **电脑主机端 (PC Windows & WSL)**：
  - Windows 原生托盘后台服务 `echo_pc_agent`，主动采集前台窗口与空闲状态，向手机端汇报桌面活动。
  - 承载 Obsidian 电脑端日常查看与编辑，通过原子 Git 事务与手机端双向无感同步。

---

## 🚀 Quick Start

> **Note**: Echogent is a highly personalized system. These steps outline the general deployment flow — you'll need to adapt persona files and configurations to your own setup.

### Prerequisites

- Android phone with [Termux](https://termux.dev/) + PRoot Ubuntu
- PC running Windows 11 with WSL2
- Python 3.10+
- [AstrBot](https://github.com/Soulter/AstrBot) 4.27+
- [NapCat](https://github.com/NapNeko/NapCatQQ) + LinuxQQ

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/makiseeee/Echogent.git
cd Echogent

# 2. Copy example configs and fill in your details
cp MEMORY.md.example MEMORY.md
cp USER.md.example USER.md
cp wenbo-profile.md.example wenbo-profile.md

# 3. Set up Python environment
python -m venv .venv
source .venv/bin/activate

# 4. Deploy to phone (via USB-first SSH)
adb forward tcp:8022 tcp:8022
ssh phone-usb
# Follow docs/operations.md for full deployment steps
```

For detailed deployment instructions, see [docs/operations.md](docs/operations.md).

---

## 🧩 Core Features

### 知识库与任务仓库 (Obsidian Vault 闭环)
- **双向 Git 同步与防抖**：手机端内置原生 Git 同步引擎 (`obsidian_git.py`)，具备后台异步推流 (`_async_push_worker`) 与 60s Pull 缓存防抖，对话回复零延迟。
- **有界安全检索**：支持 4,000 字符全文安全读取，大文件自适应滑动窗口关键词抽取，彻底杜绝上下文击穿。
- **两阶段提交 (2PC)**：新建笔记与 Wikilink 自动关联均具备预览确认机制，防误操作与数据污染。
- **每日任务自动化**：08:00 晨间任务自动出库与时间节点唤醒挂载；打勾幂等判定防重复调用；夜间 23:20 结构化晚报与习惯打卡 Streak 统计。

### 伴侣状态感知与心流决策 (Companion Awareness)
- **自然活动映射**：PC 探针捕获底层窗口标题后，自动转化为自然口语表达（如"写代码"、"查资料"、"摸鱼"、"打游戏"），拒绝机械输出窗口类名。
- **心流决策引擎 (Mind Arbiter)**：结合当前时间、光照强度（关灯检测）、独处状态与 PC 活跃度，自主判断是否主动轻声问候或保持静默陪伴。
- **人脸与光照守护**：30ms 本地人脸识别哨兵 (`face_sentry.py`) 辅助状态感知；宿舍关灯（<3 Lux）自动触发屏幕全黑睡眠模式，开灯自愈。

### 桌面 HUD 交互 (Live2D Companion Screen)
- **100% 纯离线**：MIX 2 屏幕全屏运行 Live2D 伴侣仪表盘（端口 `8099`），支持 Haru / Hiyori 动态模型与实时物理演算。
- **气泡消息镜像**：QQ 私聊对话实时同步投递至伴侣屏对话气泡，实现实体化身陪伴。

### 模型路由与双币种账本
- **动态无感切模 (`/模型`)**：支持即时热切 DeepSeek、GLM、Claude、Qwen 等主力与备用模型，无需重启服务。
- **精确计费报表 (`/使用量`)**：全局 Token 拦截器实时捕捉 Prompt Cache、输入与输出 Token，支持人民币 (CNY) 与美元 (USD) 自动折算统计。

---

## 📸 Screenshots

<!-- TODO: Add screenshots of Live2D HUD, QQ conversation, and HUD dashboard -->

> Screenshots coming soon. Stay tuned!

---

## 📁 Project Structure

```text
├── astrbot/
│   ├── data/plugins/echo-tools/    # EchoTools 核心插件 (分层解耦架构)
│   │   ├── core/                  # 配置、Token拦截器、定时Cron调度
│   │   ├── sentries/              # 电池监控、PC探针、心流决策、Live2D HUD镜像
│   │   ├── services/              # /模型切换、/使用量报表、语音转文字、安全计算器
│   │   ├── obsidian/              # Obsidian Git同步、安全检索、任务仓库管理
│   │   └── main.py                # 插件注册 Facade (<150行)
│   └── echo-persona.md            # 运行时动态编译注入的完整人设与相处准则
├── desktop_companion/             # MIX 2 纯离线 Live2D 伴侣仪表盘资源 (Haru / Hiyori)
├── echo_pc_agent/                 # Windows 托盘后台活动感知守护程序
├── scripts/                       # MIX 2 一键部署、人脸哨兵、光感守护、配置编译脚本
├── docs/                          # 系统完整技术文档库
├── tests/                         # 自动化单元测试套件
├── SOUL.md                        # Echo 核心灵魂与表达规范
├── IDENTITY.md                    # 身份元数据
├── CONTRIBUTING.md                # 贡献指南
├── CHANGELOG.md                   # 变更日志
└── SECURITY.md                    # 安全策略
```

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | 系统详细架构与消息流 |
| [Capabilities](docs/capabilities.md) | 核心能力、工具与安全边界 |
| [Operations](docs/operations.md) | 日常运维、排障与热更规范 |
| [Security](docs/security.md) | 网络拓扑、鉴权与接口安全 |
| [Roadmap](docs/roadmap.md) | 演进路线与后续规划 |
| [Obsidian Integration](docs/obsidian-integration-plan.md) | Obsidian 深度集成方案 |

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting PRs.

---

## 📄 License

This project is licensed under the **Apache License 2.0** — see the [LICENSE](LICENSE) file for details.

```
Copyright 2026 makiseeee

Licensed under the Apache License, Version 2.0
```
