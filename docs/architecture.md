# 系统详细架构与设计规范

本文档详述 **Echogent (Echo 7.0)** 的端侧拓扑、组件分工、消息链路与分层解耦模型。

---

## 1. 硬件分工与物理拓扑

### 1.1 手机端：常驻伴侣智能底座 (Xiaomi MIX 2)
- **硬件配置**：Qualcomm Snapdragon 835，6GB LPDDR4x RAM，64GB UFS 2.1，5.99 英寸 IPS 全贴合屏。
- **操作系统与运行环境**：
  - Android 9 / MIUI 底座 + Termux 原生环境。
  - Ubuntu 24.04 PRoot 容器系统，挂载于 `/opt/echo`。
  - Python 3.10+ 虚拟运行环境 `/opt/echo-astrbot`。
- **常驻服务集群**：
  - **AstrBot 核心**：端口 `6185`，驱动 LLM Agent 编排、事件调度与工具调用。
  - **LinuxQQ + NapCat**：端口 `6199` (OneBot v11 反向 WebSocket)，接入 QQ 私聊。
  - **桌面 HUD 伴侣服务**：端口 `8099`，提供 100% 离线 Live2D 动态仪表盘与实时对白气泡。
  - **人脸感知哨兵 (`face_sentry.py`)**：前置摄录 30ms 局部人脸活体探测，用于靠近唤醒。
  - **环境光敏守护 (`light_daemon.sh`)**：调用 Termux Sensor 采集光照，关灯 (<3 Lux) 自动全黑熄屏防刺眼。
  - **Mihomo 科学代理**：端口 `7890`，保障 LLM API 全球低延迟访问。

### 1.2 电脑端：活动感知与宿主主机 (PC Windows 11 & WSL)
- **宿主环境**：Windows 11 物理机 + WSL2 Ubuntu (`/home/wenbo/aaage`)。
- **常驻服务**：
  - **Echo PC Agent**：端口 `8765`，Windows 原生托盘守护进程，实时追踪当前激活窗口标题、进程名与空闲时间。
  - **Obsidian 电脑端 Vault**：主工作区，通过 Git 远程与手机端实时双向同步。
- **物理与网络通道**：
  - **USB 常驻连接 (第一优先级)**：通过 `adb forward tcp:8022 tcp:8022` 穿透，SSH 速度达 30MB/s，0 丢包。
  - **ZeroTier 虚拟局域网 (第二优先级)**：手机 `10.144.13.0` 与电脑 `10.144.232.236`，提供外出无物理连线时的远程兜底。

---

## 2. 系统消息流与交互链路

```text
[用户 QQ 私聊]
      │
      ▼
[手机 NapCat / LinuxQQ]
      │ (OneBot v11 WebSocket: 127.0.0.1:6199)
      ▼
[手机 AstrBot 核心引擎]
      │
      ├─► [Token 拦截器 (core/token_interceptor.py)] ── 记录双币种计费至 SQLite
      │
      ├─► [PC 状态注入器] ◄── (HTTP GET :8765/status) ── [PC Windows Agent (前台活动)]
      │
      ├─► [心流决策引擎 (sentries/mind_arbiter.py)] ── 结合时间/光照/独处触发主动关怀
      │
      ├─► [Obsidian 任务与知识库] ◄── (Git 异步推拉) ── [Gitee 远端 / PC Vault]
      │
      ├─► [LLM 供应商] ── (DeepSeek / GLM / Claude 经 7890 代理推理)
      │
      ▼
[回复流式分段与净化 (Streaming Segmenter)]
      │
      ├─► [NapCat QQ 私聊发送] ── (纯口语 + 独立行 X 岛颜文字)
      │
      └─► [Live2D HUD 伴侣屏] ── (HTTP POST :8099/api/bubble 同步投递角色气泡)
```

---

## 3. EchoTools 核心插件分层解耦架构

为了彻底消除历史近 2,000 行的“上帝类”隐患，`echo-tools` 采用清晰的分层微模块结构：

```text
astrbot/data/plugins/echo-tools/
├── main.py                     # [Facade] AstrBot 声明层，仅负责指令分发与事件转派 (<150行)
├── metadata.yaml               # 插件规范与版本信息
├── core/                       # [基础设施层]
│   ├── config.py               # 环境变量、路径解析与全局权限鉴权
│   ├── token_interceptor.py    # OpenAI SDK 劫持、动态费率换算与 SQLite 账本写入
│   ├── persona_compiler.py     # SOUL.md + RELATIONSHIP.md 编译同步
│   └── cron_scheduler.py       # 晨报 (08:00)、晚报 (23:20) 及 schedule_wakeup 挂载
├── sentries/                   # [状态与感知守护层]
│   ├── supervisor.py           # 守护任务监督器（统一负责 start / cancel / status）
│   ├── battery_sentry.py       # MIX 2 电池电量、温度监测与低电预警
│   ├── pc_prober.py            # PC 存活探测、网络唤醒 (WOL) 与前台窗口自然化映射
│   ├── mind_arbiter.py         # 光感睡眠检测、长时独处判定与自主主动发言决策
│   └── companion_hud.py        # Live2D 屏幕气泡推送 (8099) 与今日待办数据导出
├── services/                   # [纯业务服务层 (0 框架依赖，便于单元测试)]
│   ├── model_switcher.py       # /模型 动态模型列表查询与运行时 Provider 热切
│   ├── usage_reporter.py       # /使用量 双币种消费报表生成
│   ├── voice_transcriber.py    # QQ 语音转文字 (SenseVoice / Whisper 本地与远程服务)
│   └── safe_calculator.py      # AST 白名单安全四则运算求解器
└── obsidian/                   # [知识库与任务管理层]
    ├── obsidian_facade.py      # 两阶段提交 (2PC) 事务协调、范围校验与错误包装
    ├── obsidian_access.py      # 路径策略与访问权限鉴权
    ├── obsidian_search.py      # 4000 字符有界读取与滑动窗口关键词检索
    ├── obsidian_write.py       # 原子写入、幂等追加与 Wikilink 安全插入
    ├── obsidian_git.py         # 异步 Push 与 Pull 缓存防抖
    └── daily_task_manager.py   # 任务仓库出库、打勾幂等判定、日终复盘与打卡 Streak
```

---

## 4. 数据分布与真实副本权威 (SSOT)

| 数据类别 | 权威主副本位置 | 同步与备份机制 |
|---|---|---|
| **长程记忆与关系** | 手机 `/opt/echo/data/data_v4.db` | 本地 SQLite WAL 模式，夜间批处理自动蒸馏 |
| **Token 消费账本** | 手机 `/opt/echo/data/echo-tools-token-usage.db` | 每次 LLM 请求后由拦截器实时写入 |
| **Obsidian Vault** | 手机与 PC 平等双主副本 | 依托 Git 远程仓库，通过原子事务与缓存防抖双向同步 |
| **核心人格与相处准则** | Git 仓库 `SOUL.md` / `RELATIONSHIP.md` | 由编译脚本自动合成为 `echo-persona.md` 并注入 AstrBot |
| **PC 实时活动状态** | PC 内存 (`echo_pc_agent`) | 手机端按需轮询，不落盘存储，严格保护隐私 |

---

## 5. 故障隔离与降级保障

1. **PC 关机或休眠**：
   - 手机端 QQ 对话、Obsidian 知识库检索、定时任务与已有记忆完全不受影响。
   - Agent 自动感知 PC 离线，停止尝试获取窗口标题，并支持通过 `/wol` 指令远程唤醒电脑。
2. **手机网络波动**：
   - 依赖 USB ADB 反向代理保障手机端网络畅通；若断网，后台 Git 提交自动保留在本地队列，待网络恢复后在下一次写操作或定时周期自动追溯推送。
3. **伴侣屏或传感器异常**：
   - Live2D HUD 或人脸哨兵若出现异常退出，守护进程独立记录日志，主对话引擎完全不受干扰。
