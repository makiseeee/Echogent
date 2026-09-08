# 演进路线与待办清单

本文档跟踪 **Echogent (Echo 7.0)** 已达成里程碑、正在推进的工程重构与后续演进目标。

---

## 1. 已达成里程碑 (Completed Milestones)

- [x] **硬件平台升级**：由旧机成功迁移至 Xiaomi MIX 2 (Snapdragon 835, 6GB RAM)，完成 Termux + PRoot Ubuntu 全量部署。
- [x] **物理高速直连**：确立并实施 **USB-First 运维准则**，利用 ADB 端口转发实现低延迟、零丢包的本地开发与排障通道。
- [x] **离线 Live2D 伴侣屏**：完成 100% 纯离线 Live2D HUD 仪表盘构建（端口 `8099`），实现 QQ 消息与伴侣屏角色对白气泡实时镜像。
- [x] **物理环境感知守护**：30ms 本地人脸活体哨兵 (`face_sentry.py`) 与宿舍关灯（<3 Lux）全黑睡眠守护机制 (`light_daemon.sh`) 上线。
- [x] **Obsidian 闭环原生落地**：
  - 手机端原生 Git 同步引擎与异步推流 Worker；
  - 4,000 字符有界安全读取与滑动窗口关键词检索；
  - 每日待办出库调度、打勾状态幂等校验与习惯打卡 Streak 统计。
- [x] **主动生活与复盘系统**：08:00 晨间任务自动出库与带时分任务自动定时挂载；23:20 结构化晚间深度复盘与 Thino 灵感共鸣。
- [x] **模型与资产控制**：动态 `/模型` 切换与实时双币种 (CNY/USD) Token 计量账本 (`/使用量`)。
- [x] **三端版本库全面统一**：手机端生产代码、PC WSL 与 GitHub `origin/main` 代码库实现 100% 双向对齐与同步。
- [x] **`EchoTools 2.0.0` 上帝类解耦与微模块化**：
  - 将 1,951 行单文件彻底解耦拆分为 `core/`、`sentries/`、`services/`、`obsidian/` 微模块分层架构，入口 Facade 瘦身至 ~270 行，保持外部 Tool/Command 接口 100% 契约不变；
  - 编写并扩充单元测试套件 (`pytest tests/`)，25/25 单元测试全绿通过。
- [x] **高危安全边界加固与 DoS 熔断**：
  - `SafeCalculator` 增加指数 $\le 1000$ 与阶乘 $\le 100$ 双重规模熔断，防范 BigInt DoS；
  - `WebFetcher` 引入递归 IP 解析与私网/回环地址深度拦截（防御 SSRF），针对 Clash/Mihomo Fake-IP `198.18.0.0/15` 正确白名单放行；
  - PC Agent 增加 Bearer `ECHO_PC_TOKEN` 鉴权中间件、CORS 域名收紧及 1s 采样节流；
  - 部署脚本升级为单流 `.tar.gz` 传输并支持保留 NapCat 的轻量重启。
- [x] **高频性能瓶颈专项优化**：
  - 全局共享 `HttpClient` (`aiohttp.ClientSession`) 消除每 20s 探针和每条气泡的 TCP+TLS 握手浪费；
  - Obsidian `pull_if_stale(30.0)` 防抖节流，杜绝大模型连续读写任务时的 Gitee 网络等待；
  - `obsidian_search.py` 与 `core/config.py` 基于 `st_mtime` 内存缓存，消除 eMMC 闪存全量 I/O。

---

## 2. 架构演进与推进中的核心任务 (In Progress / Next Up)

> **核心原则**：坚决保持 **AstrBot 平台底座** 不动摇，不搞脱离生态的自研协议层，将现代化软件工程模式（FTS5、Pub/Sub、WebSocket）作为积木有机沉淀进插件微模块内部。

- [ ] **P1: 消除 Obsidian 代码双生 (Code Unification)**：
  - **现状**：`mcp-executor/` 与 `echo-tools/obsidian/` 存在两份并行的 Obsidian/DailyTask 代码，修改容易产生漏改。
  - **方案**：将 `echo-tools/obsidian/` 确立为唯一真相源 (SSOT)，`mcp-executor` 改造为通过 `sys.path` 直接 import 共享模块，清理冗余代码文件。

- [ ] **P2: Obsidian 本地 SQLite FTS5 全文索引引擎 (BM25 毫秒检索)**：
  - **现状**：当前 `search_vault` 已具备 mtime 缓存，但在笔记库规模进一步扩大后，冷启动检索仍是暴力子串匹配。
  - **方案**：利用 Python 原生内置的 `sqlite3` FTS5 引擎，为 Obsidian 知识库建立增量全文检索库（`.vault_index.db`）；在 `git pull` 后通过 diff 进行增量索引重建，提供真正的中文分词、BM25 相关性评分与 <5ms 极速检索，保留原 rglob 暴力搜索作为优雅降级。

- [ ] **P3: 哨兵微模块轻量 Pub/Sub 进程内事件总线 (`core/event_bus.py`)**：
  - **现状**：`MindArbiter` 直接持有了 `BatterySentry`、`PCProber` 的实例引用并进行深层回调透传，存在紧耦合。
  - **方案**：在 `core/` 下用纯 Python 标准库编写 <100 行轻量 `EventBus`（零额外依赖，拒绝 ZeroMQ 重型 C 扩展）。各哨兵改为发布事件（如 `battery.low`、`pc.activity_updated`），心智调度与 HUD 按需订阅，实现完全解耦与新硬件传感器零侵入扩展。

- [ ] **P4: PC Agent 从“手机定时轮询”升级为“PC 变化主动推送 (WebSocket)”**：
  - **现状**：手机端每 20 秒向 PC 发送 HTTP GET 探测活动状态，PC 静止时存在无意义心跳空转。
  - **方案**：PC 端 `echo_pc_agent` 增设 `/ws/activity` WebSocket 长连接端点，仅在检测到前台窗口、应用或锁屏状态发生变化时才向手机推送事件；手机端复用 `HttpClient.get_session().ws_connect()` 挂载监听，实现零空转开销与毫秒级情境感知。

- [ ] **P5: 手机数据自动化一致性备份**：
  - 编写 SQLite WAL 模式安全热备脚本，避免文件级复制导致数据库损坏；
  - 定时通过 USB / SSH 将手机 `data_v4.db`、`echo-tools-token-usage.db` 拉回电脑端建立轮转归档。

- [ ] **P6: 锂电池养护与智能插座自动通断**：
  - 联动智能插座 API（如米家接入），根据手机电量监测守护：低于 40% 自动通电，达到 80% 自动断电，保护常驻设备电池健康。

---

## 3. 中远期演化规划 (Future Roadmap)

- [ ] **P7: 本地多模态视觉快照**：
  - 结合前置摄像头，在特定互动或定时场景下轻量捕捉环境画面，提供“看看我在干嘛”的原生多模态视觉感知。
- [ ] **P8: 记忆系统图谱化与自主遗忘机制**：
  - 沉淀高密度长程记忆图谱，实现基于情绪和事件关联的非线性记忆检索与自我整理。
