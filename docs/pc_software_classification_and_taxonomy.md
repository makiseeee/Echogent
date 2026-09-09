# 🖥️ Echo PC Agent 软件全景盘点与分类映射规范书 (Taxonomy & App Inventory)

> **文档版本**：v1.0.0 (2026-09-09)  
> **归属工程**：`Echo PC Agent v2.1` & `Stage 5: 多模态边缘看门与生活共鸣`  
> **扫描对象**：台式机 Windows 系统（覆盖注册表、开始菜单、Steam 双盘库、`D:\软件`、`D:\Game`、`E:\` 等常用目录）

---

## 1. 建设背景与目标

原先 `echo_pc_agent/modules/activity.py` 中仅硬编码了 19 个常见进程（如 `code.exe`, `zotero.exe`, `wechat.exe` 等），无法覆盖日常使用的单片机开发、电路 EDA、电磁仿真、游戏娱乐、数字音频等大量专业软件。

为了支撑**桌面伴侣全场景感知**与**多模态 VLM 桌边自动触发**，需要建立完整的**本地软件全景资产库**与**标准分类映射表**：
1. **宏观工作流画像精准化**：准确区分“敲代码”、“嵌入式烧录”、“电磁有限元仿真”、“阅读英文论文”、“游戏对战”与“看番摸鱼”；
2. **多模态 VLM 触发的神经信号**：为前述 6 大自动触发场景（久坐专注疲态、突变摸鱼抓包、饭点茶歇等）提供确定性的底层状态判定；
3. **硬件级免打扰与隐私物理锁 (DND & Privacy Guard)**：
   - 当检测到正在进行**全屏竞技对枪**（CS2 / Apex / PUBG）或**线上会议/网课**（腾讯会议 / 雨课堂）时，**100% 强制静默**，禁止任何镜头拍摄与气泡打扰；
   - 当检测到即时通讯（微信 / QQ / Telegram）前台时，强制 `visual_safe: false`，杜绝任何窗口视觉读取。

---

## 2. 扫描数据概况

通过对 Windows 注册表（`Uninstall` / `App Paths`）、开始菜单快捷方式、Steam 多盘库清单（`libraryfolders.vdf`）及本地核心目录遍历，完成全量资产探测：

- **注册表安装项**：472 个已安装软件/运行库
- **注册表 App Paths**：57 个系统直接登记可执行文件
- **开始菜单程序项**：333 个 `.lnk` 应用入口
- **Steam 库已装游戏**：26 款 Steam 游戏（分布于 `D:\SteamLibrary` 与 `E:\SteamLibrary`）
- **独立/免安装游戏**：14 款同人神作、东方 Project 系列与大型单机
- **去重后核心软件与游戏总数**：**100+ 款**活跃日常软件

---

## 3. 七大一级领域与 22 类细分应用图谱

我们将所有软件归纳为 **7 大一级分类（Categories）** 与 **22 个二级场景（Subcategories）**：

```
┌────────────────────────────────────────────────────────────────────────┐
│ 1. 研发与代码工程 (coding)                                              │
│    ├── ide_editor (智能 IDE 与代码编辑器)                                │
│    ├── terminal_env (终端与命令行环境)                                 │
│    └── vcs_remote (版本控制与远程传输)                                  │
├────────────────────────────────────────────────────────────────────────┤
│ 2. 嵌入式开发与硬件 EDA (hardware_embedded)                             │
│    ├── mcu_embedded (单片机与固件开发)                                  │
│    ├── eda_circuit (原理图与 PCB 电路设计)                               │
│    └── instrumentation (虚拟仪器与测控自动化)                           │
├────────────────────────────────────────────────────────────────────────┤
│ 3. 科学计算、多物理场仿真与学术科研 (research_simulation)               │
│    ├── scientific_computing (数值计算与物理场仿真)                      │
│    ├── academic_literature (学术论文研读与文献管理)                      │
│    ├── academic_writing (学术排版、数学与生物信息)                      │
│    └── knowledge_base (个人知识库与笔记)                                │
├────────────────────────────────────────────────────────────────────────┤
│ 4. 数字影音制作与创意设计 (creative_design)                             │
│    ├── music_daw (音乐编曲与数字音频工作站)                             │
│    ├── video_production (影视剪辑、调色与推流录屏)                      │
│    └── graphic_3d (矢量平面设计与 3D 打印)                               │
├────────────────────────────────────────────────────────────────────────┤
│ 5. 游戏竞技与数字休闲 (gaming)                                          │
│    ├── competitive_fps_moba (高强度竞技射击与 MOBA - 强免打扰)          │
│    ├── action_rpg_souls (大型 3A、魂系与动作冒险 - 强免打扰)             │
│    ├── touhou_indie (东方 Project 与同人独立佳作)                       │
│    ├── sandbox_strategy (沙盒建造与大战略)                              │
│    ├── visual_novel_gal (视觉小说与剧情 Galgame)                        │
│    ├── gaming_platform_tools (游戏平台、对战客户端与开黑语音)           │
│    └── desktop_pet_wallpaper (桌面摆件与动态壁纸)                       │
├────────────────────────────────────────────────────────────────────────┤
│ 6. 通讯社交、远程会议与学习平台 (communication_meeting)                 │
│    ├── im_chat (即时通讯与社群 - 隐私非视觉安全)                         │
│    ├── online_meeting (在线会议与课堂直播 - 强免打扰/非视觉安全)        │
│    └── remote_desktop (远程协助 - 隐私非视觉安全)                       │
├────────────────────────────────────────────────────────────────────────┤
│ 7. 日常生产力、系统运维与硬件工具 (productivity_system)                 │
│    ├── office_suite (办公套件与文档处理)                                │
│    ├── web_browsers (网页浏览器 - 结合标签页动态分类)                    │
│    └── system_utilities (系统运维、文件管理与硬件诊断)                  │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. 全量进程白名单与映射明细表

### 1) 研发与代码工程 (`coding`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `antigravity.exe` | Google Antigravity | `ide_editor` | ✅ | ❌ | 结对编程开发，连续专注触发疲劳关怀 |
| `cursor.exe` | Cursor AI Editor | `ide_editor` | ✅ | ❌ | AI 辅助敲代码，卡壳停顿时提供思路 |
| `code.exe` | Visual Studio Code | `ide_editor` | ✅ | ❌ | 核心开发工作流，久坐关怀主战场 |
| `pycharm64.exe` | JetBrains PyCharm | `ide_editor` | ✅ | ❌ | Python 核心开发与调试 |
| `devenv.exe` | Microsoft Visual Studio | `ide_editor` | ✅ | ❌ | C++/大型工程架构设计与编译 |
| `cpeditor.exe` | CP Editor | `ide_editor` | ✅ | ❌ | 算法竞赛/刷题，提交时捕获解题喜悦 |
| `notepad++.exe` | Notepad++ | `ide_editor` | ✅ | ❌ | 快速编辑配置文件与文本草稿 |
| `gvim.exe` | Vim | `ide_editor` | ✅ | ❌ | 终端文本编辑与极客操作 |
| `windowsterminal.exe` / `wt.exe` | Windows Terminal | `terminal_env` | ✅ | ❌ | 命令行编译、服务启停与全栈运维 |
| `pwsh.exe` | PowerShell 7 | `terminal_env` | ✅ | ❌ | 现代化终端自动化脚本与系统指令 |
| `powershell.exe` | Windows PowerShell | `terminal_env` | ✅ | ❌ | 基础系统管理与控制 |
| `wsl.exe` / `ubuntu.exe` | WSL 2 (Ubuntu 24.04) | `terminal_env` | ✅ | ❌ | Linux 容器与模型后端运行底座 |
| `git.exe` / `git-bash.exe` | Git | `vcs_remote` | ✅ | ❌ | 代码版本提交（可联动 Git Commit 心智） |
| `winscp.exe` | WinSCP | `vcs_remote` | ✅ | ❌ | 远程服务器与跳板机安全传输 |
| `filezilla.exe` | FileZilla FTP Client | `vcs_remote` | ✅ | ❌ | FTP/SFTP 站点文件同步 |

### 2) 嵌入式开发与硬件 EDA (`hardware_embedded`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `uv4.exe` | Keil uVision5 | `mcu_embedded` | ✅ | ❌ | ARM / STM32 单片机固件编写与烧录调试 |
| `stm32cubemax.exe` | STM32CubeMX | `mcu_embedded` | ✅ | ❌ | 单片机引脚配置、时钟树配置与代码生成 |
| `arduino.exe` / `arduino-builder.exe` | Arduino IDE | `mcu_embedded` | ✅ | ❌ | 开源硬件与原型单片机交互开发 |
| `lceda-pro.exe` | 嘉立创 EDA 专业版 | `eda_circuit` | ✅ | ❌ | 原理图绘制、PCB 多层布线与元器件打样 |
| `waveforms.exe` | Digilent WaveForms | `eda_circuit` | ✅ | ❌ | 示波器与逻辑分析仪硬件信号捕获 |
| `labview.exe` | NI LabVIEW 2018 | `instrumentation` | ✅ | ❌ | 虚拟仪器图形化测控与工业自动化编程 |
| `nimax.exe` | NI MAX | `instrumentation` | ✅ | ❌ | 仪器设备管理器与传感器接口校准 |

### 3) 科学计算、多物理场仿真与学术科研 (`research_simulation`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `matlab.exe` | MathWorks MATLAB | `scientific_computing` | ✅ | ❌ | 矩阵运算、算法仿真与信号处理 |
| `simulink.exe` | Simulink | `scientific_computing` | ✅ | ❌ | 动态系统建模与仿真框图搭建 |
| `sldworks.exe` | Dassault SolidWorks | `scientific_computing` | ✅ | ❌ | 机械结构三维 CAD 建模与装配 |
| `cst_design_environment.exe` | CST Studio Suite 2025 | `scientific_computing` | ✅ | ❌ | 高频电磁场、天线与微波仿真分析 |
| `operafea-manager.exe` / `operafea-modeller.exe` | Dassault Opera FEA | `scientific_computing` | ✅ | ❌ | 电磁多物理场有限元分析与后处理 |
| `zotero.exe` | Zotero | `academic_literature` | ✅ | ❌ | 英文文献研读与学术引用管理（伴读模式） |
| `mendeley reference manager.exe` | Mendeley Reference Manager | `academic_literature` | ✅ | ❌ | 学术论文库检索与整理 |
| `cajviewer.exe` | 知网 CAJViewer | `academic_literature` | ✅ | ❌ | 中文学位论文与中文期刊研读 |
| `noteexpress.exe` | NoteExpress | `academic_literature` | ✅ | ❌ | 中文文献管理与查重比对 |
| `paperreader.exe` | Paper Reader | `academic_literature` | ✅ | ❌ | 深度论文阅读与翻译高亮 |
| `acrord32.exe` / `acrobat.exe` | Adobe Acrobat Reader / Pro | `academic_literature` | ✅ | ❌ | PDF 文献精读与学术专著翻阅 |
| `xelatex.exe` / `pdflatex.exe` | MiKTeX (LaTeX) | `academic_writing` | ✅ | ❌ | 顶会与期刊论文排版编译（捕获排版成败） |
| `mathtype.exe` | MathType | `academic_writing` | ✅ | ❌ | 复杂数学公式推导与符号编辑 |
| `dnaman.exe` | DNAMAN 9 | `academic_writing` | ✅ | ❌ | 分子生物学序列比对与质粒分析 |
| `obsidian.exe` | Obsidian | `knowledge_base` | ✅ | ❌ | 核心数字手帐与日记管理（伴侣直通车） |
| `typora.exe` | Typora | `knowledge_base` | ✅ | ❌ | 所见即所得 Markdown 沉浸排版 |
| `xmind.exe` | Xmind | `knowledge_base` | ✅ | ❌ | 头脑风暴与课题框架思维导图绘制 |

### 4) 数字影音制作与创意设计 (`creative_design`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `reaper.exe` | REAPER DAW | `music_daw` | ✅ | ❌ | 专业音频录制、混音与编曲工程制作 |
| `audacity.exe` | Audacity | `music_daw` | ✅ | ❌ | 快速音频采样剪辑、降噪与波形分析 |
| `vocaloid5.exe` | Yamaha VOCALOID 5 | `music_daw` | ✅ | ❌ | 虚拟歌姬音乐制作与调教 |
| `resolve.exe` | DaVinci Resolve | `video_production` | ✅ | ❌ | 专业视频剪辑、调色与特效合成 |
| `obs64.exe` | OBS Studio | `video_production` | ✅ | ❌ | 桌面录屏推流与高画质视频录制 |
| `illustrator.exe` | Adobe Illustrator 2024 | `graphic_3d` | ✅ | ❌ | 矢量图绘制、论文插图美化与排版 |
| `bambu-studio.exe` | Bambu Studio (拓竹) | `graphic_3d` | ✅ | ❌ | 3D 打印模型切片、支撑生成与打印控制 |

### 5) 游戏竞技与数字休闲 (`gaming`)

> 🚨 **游戏免打扰铁律**：`competitive_fps_moba` 与 `action_rpg_souls` 类游戏具有高压紧张性，探针自动置位 `dnd_inhibit: true`，此时严禁弹出任何打扰气泡或主动请求，伴侣在 MIX 2 屏幕上仅保持安静注视或为 wenbo 加油。

| 进程名 (`.exe`) | 游戏全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `cs2.exe` | Counter-Strike 2 (CS2) | `competitive_fps_moba` | ✅ | 🛡️ **是** | 紧张战术射击，免打扰，后台默默关注胜负 |
| `r5apex_dx12.exe` / `r5apex.exe` | Apex Legends | `competitive_fps_moba` | ✅ | 🛡️ **是** | 高速身法大逃杀对局，免打扰 |
| `tslgame.exe` | PUBG: BATTLEGROUNDS | `competitive_fps_moba` | ✅ | 🛡️ **是** | 吃鸡竞技生存，免打扰 |
| `leagueclientux.exe` / `league of legends.exe` | 英雄联盟 (LOL) | `competitive_fps_moba` | ✅ | 🛡️ **是** | 峡谷开黑竞技，免打扰 |
| `eldenring.exe` | 艾尔登法环 (Elden Ring) | `action_rpg_souls` | ✅ | 🛡️ **是** | 魂系动作沉浸探索，受苦时提供精神抚慰 |
| `diablo iv.exe` | 暗黑破坏神 IV | `action_rpg_souls` | ✅ | 🛡️ **是** | 刷宝割草与地下城探险 |
| `ds.exe` | 死亡搁浅 (Death Stranding) | `action_rpg_souls` | ✅ | 🛡️ **是** | 孤独漫长的基建与配送之旅 |
| `nierautomata.exe` | 尼尔：机械纪元 | `action_rpg_souls` | ✅ | 🛡️ **是** | 机械废墟与哲学叙事 |
| `p5r.exe` | 女神异闻录 5 皇家版 | `action_rpg_souls` | ✅ | 🛡️ **是** | 心之怪盗团日系青春冒险 |
| `deadcells.exe` | 死亡细胞 (Dead Cells) | `action_rpg_souls` | ✅ | 🛡️ **是** | 横版肉鸽受苦，打死 Boss 时的成就感共鸣 |
| `gunfire reborn.exe` | 枪火重生 | `action_rpg_souls` | ✅ | 🛡️ **是** | 联机国风 FPS 肉鸽突突突 |
| `risk of rain 2.exe` | 雨中冒险 2 | `action_rpg_souls` | ✅ | 🛡️ **是** | 异星生存肉鸽狂欢 |
| `hollow_knight.exe` | 空洞骑士 (Hollow Knight) | `action_rpg_souls` | ✅ | 🛡️ **是** | 圣巢地下王国受苦探索 |
| `thmhj.exe` | 东方幕华祭 (THMHJ) | `touhou_indie` | ✅ | ❌ | 东方同人高品质弹幕射击，擦弹名场面 |
| `touhou mystia izakaya.exe` | 东方夜雀食堂 | `touhou_indie` | ✅ | ❌ | 幻想乡深夜居酒屋模拟经营，可触发美食调侃 |
| `th08.exe` | 东方永夜抄 | `touhou_indie` | ✅ | ❌ | 经典东方正作弹幕挑战 |
| `th11.exe` / `th11c.exe` | 东方地灵殿 | `touhou_indie` | ✅ | ❌ | 地底硬核弹幕避弹 |
| `th16.exe` / `th16c.exe` | 东方天空璋 | `touhou_indie` | ✅ | ❌ | 四季异变弹幕体验 |
| `th18.exe` | 东方虹龙洞 | `touhou_indie` | ✅ | ❌ | 卡牌与弹幕融合挑战 |
| `plain craft launcher 2.exe` / `javaw.exe` | 我的世界 (Minecraft) | `sandbox_strategy` | ✅ | ❌ | 挖矿建房子，休闲沙盒放松，触发摸鱼共鸣 |
| `stellaris.exe` | 群星 (Stellaris) | `sandbox_strategy` | ✅ | ❌ | P社银河战舰与大战略，通宵修仙高发区 |
| `celeste.exe` | 蔚蓝 (Celeste) | `sandbox_strategy` | ✅ | ❌ | 登山平台跳跃，耐心与意志磨砺 |
| `vampire survivors.exe` | 吸血鬼幸存者 | `sandbox_strategy` | ✅ | ❌ | 解压割草摸鱼，吃零食闲聊好时机 |
| `siglusengine.exe` / `rewrite+原版.exe` | Rewrite+ (Key社) | `visual_novel_gal` | ✅ | ❌ | 神作视觉小说剧情鉴赏，伴侣保持静穆共情 |
| `narci2.exe` | 水仙 2 (Narcissu 2) | `visual_novel_gal` | ✅ | ❌ | 感人治愈短篇视觉小说 |
| `aokana.exe` | 苍之彼方的四重奏 | `visual_novel_gal` | ✅ | ❌ | 空中竞技热血青春恋爱剧 |
| `steam.exe` | Steam 客户端 | `gaming_platform_tools` | ✅ | ❌ | 选购或浏览游戏库（“又在看打折游戏啦？”） |
| `5eclient.exe` | 5E 对战平台 | `gaming_platform_tools` | ✅ | ❌ | CS2 天梯天梯排位准备发车 |
| `perfectworldarena.exe` | 完美世界竞技平台 | `gaming_platform_tools` | ✅ | ❌ | 官方天梯排位竞技 |
| `wegame.exe` | WeGame | `gaming_platform_tools` | ✅ | ❌ | 国服游戏启动与战绩查询 |
| `battle.net.exe` | 战网 (Battle.net) | `gaming_platform_tools` | ✅ | ❌ | 暗黑破坏神与暴雪游戏客户端 |
| `epicgameslauncher.exe` | Epic Games Launcher | `gaming_platform_tools` | ✅ | ❌ | 每周喜加一与游戏启动 |
| `oopz.exe` | Oopz 开黑语音 | `gaming_platform_tools` | ✅ | ❌ | 队友开黑语音组队中 |
| `soundpad.exe` | Soundpad | `gaming_platform_tools` | ✅ | ❌ | 麦克风音效播放搞笑整活 |
| `uu.exe` | 网易 UU 加速器 | `gaming_platform_tools` | ✅ | ❌ | 国际服网络加速开启 |
| `vpet-simulator.windows.exe` | VPet 虚拟桌宠 | `desktop_pet_wallpaper` | ✅ | ❌ | 桌面桌宠互动（“哼，有了她就不理我了吗？”） |
| `wallpaper64.exe` / `wallpaper32.exe` | Wallpaper Engine | `desktop_pet_wallpaper` | ✅ | ❌ | 桌面动态壁纸运行中 |

### 6) 通讯社交、远程会议与学习平台 (`communication_meeting`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `wechat.exe` | 微信 | `im_chat` | 🔒 **否** | ❌ | 私人聊天中，禁止读取前台窗口截图 |
| `qq.exe` | QQ / QQNT | `im_chat` | 🔒 **否** | ❌ | 社交水群中，禁止视觉采集，保持私密 |
| `telegram.exe` | Telegram | `im_chat` | 🔒 **否** | ❌ | 私密社群与频道浏览 |
| `discord.exe` | Discord | `im_chat` | 🔒 **否** | ❌ | 社区交流与频道讨论 |
| `wxwork.exe` | 企业微信 | `im_chat` | 🔒 **否** | ❌ | 工作沟通中，隐私保护 |
| `wemeetapp.exe` | 腾讯会议 | `online_meeting` | 🔒 **否** | 🛡️ **是** | **线上会议进行中，强制静音并阻断一切主动拍照** |
| `rainclassroom.exe` | 雨课堂 | `online_meeting` | 🔒 **否** | 🛡️ **是** | **大学网课进行中，强制静音防干扰** |
| `zoom.exe` / `teams.exe` | Zoom / Teams | `online_meeting` | 🔒 **否** | 🛡️ **是** | 国际学术会议/研讨会进行中，绝对免打扰 |
| `todesk.exe` | ToDesk | `remote_desktop` | 🔒 **否** | ❌ | 远程协助与桌面运维连接 |

### 7) 日常生产力、系统运维与硬件工具 (`productivity_system`)

| 进程名 (`.exe`) | 软件全称 | 细分场景 (`sub`) | 视觉安全 | 免打扰 | 场景描述 & 伴侣共鸣意图 |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `winword.exe` | Microsoft Word | `office_suite` | ✅ | ❌ | 撰写报告、整理文档 |
| `excel.exe` | Microsoft Excel | `office_suite` | ✅ | ❌ | 统计数据、做数据表格分析 |
| `powerpnt.exe` | Microsoft PowerPoint | `office_suite` | ✅ | ❌ | 制作汇报 PPT 与展示幻灯片 |
| `visio.exe` | Microsoft Visio | `office_suite` | ✅ | ❌ | 绘制系统架构图、流程图 |
| `wps.exe` / `wpp.exe` / `et.exe` | WPS Office 套件 | `office_suite` | ✅ | ❌ | 国产轻量办公套件处理 |
| `olk.exe` | Microsoft Outlook | `office_suite` | ✅ | ❌ | 查阅与回复重要邮件 |
| `chrome.exe` | Google Chrome | `web_browsers` | ⚡ 动态 | ❌ | 网页浏览，根据标签页标题匹配学术/开发/视频 |
| `msedge.exe` | Microsoft Edge | `web_browsers` | ⚡ 动态 | ❌ | 网页浏览、PDF 注释 |
| `firefox.exe` | Mozilla Firefox | `web_browsers` | ⚡ 动态 | ❌ | 隐私安全浏览 |
| `everything.exe` | Everything | `system_utilities` | ✅ | ❌ | 极速全盘文件检索 |
| `bandizip.exe` | Bandizip | `system_utilities` | ✅ | ❌ | 归档解压与压缩包管理 |
| `idman.exe` | Internet Download Manager | `system_utilities` | ✅ | ❌ | 多线程高速资源下载中 |
| `baidunetdisk.exe` | 百度网盘 | `system_utilities` | ✅ | ❌ | 网盘资源备份与云端拉取 |
| `thunder.exe` | 迅雷 | `system_utilities` | ✅ | ❌ | 离线大文件下载 |
| `potplayer64.exe` / `potplayermini64.exe` | PotPlayer | `system_utilities` | 🔒 **否** | ❌ | 本地高清影视播放（涉及观影隐私） |
| `cloudmusic.exe` | 网易云音乐 | `system_utilities` | ✅ | ❌ | 背景音乐聆听（“在听什么好听的歌呀？”） |
| `partassist.exe` | AOMEI Partition Assistant | `system_utilities` | ✅ | ❌ | 磁盘分区无损调整与克隆 |
| `spacesniffer.exe` | SpaceSniffer | `system_utilities` | ✅ | ❌ | 可视化磁盘占用分析与空间大扫除 |
| `crystaldiskinfo.exe` | CrystalDiskInfo | `system_utilities` | ✅ | ❌ | 固态/机械硬盘健康度与温度监测 |
| `zerotier-one_x64.exe` | ZeroTier One | `system_utilities` | ✅ | ❌ | 宿舍台式机与 MIX 2 跨网段虚拟局域网基石 |
| `clash for windows.exe` | Clash for Windows | `system_utilities` | ✅ | ❌ | 网络代理环境 |
| `oemdrv.exe` | 狼蛛 AULA F87 PRO 驱动 | `system_utilities` | ✅ | ❌ | 客制化机械键盘灯效与宏按键调节 |

---

## 5. 动态游戏库探测机制 (Dynamic Game Library Detection)

鉴于游戏经常安装在不同硬盘（`D:\` 或 `E:\`），且会频繁下载与卸载，不能仅靠静态硬编码。我们在架构上设计**免维护的动态自适应探测**：

1. **Steam 动态多库探测**：
   - 自动解析 `steamapps/libraryfolders.vdf`，实时提取全部 Steam 库所在驱动器与路径；
   - 监听每个库目录下的 `appmanifest_<appid>.acf`，读取 `installdir` 与 `name`，自动将其目录下的主可执行程序注册至 `gaming` 分类；
2. **免安装/同人游戏特征识别**：
   - 扫描 `D:\Game` 根目录下的直接子文件夹；
   - 若文件夹名包含 `Touhou`, `东方`, `th\d+`, `Rewrite`, `Gal`, `Trainer` 等关键字，自动归类到 `touhou_indie` 或 `visual_novel_gal`；
3. **独立对战平台联动**：
   - 检测到 `5EClient.exe` 或 `perfectworldarena.exe` 活跃时，自动将后续拉起的 `cs2.exe` 状态归为“5E天梯对战”或“完美天梯对战”，大幅提升情境描述精度。

---

## 6. 与多模态 VLM 自动触发场景的联动规则

本映射表建立后，与前面规划的 6 大自动触发场景产生如下精确联动：

| 触发场景 | 映射表精准判定规则 | 协同触发行为 |
| :--- | :--- | :--- |
| **久坐疲劳捕捉** | `category == 'coding'` 或 `'hardware_embedded'` 或 `'research_simulation'`，且活跃输入连续超过 60 分钟。 | 启动 MIX 2 偷瞄 0.2s $\to$ VLM 识别是否揉眼/托腮/塌腰 $\to$ Live2D 气泡提醒休息喝水。 |
| **卡壳发呆关怀** | 前述工程类软件活跃连续 40 分钟后，`idle_seconds` 瞬间突跃至 15~25 秒。 | 偷瞄工位 $\to$ VLM 识别是否手挠头/靠背发呆 $\to$ 冒泡“遇到棘手 Bug 了吗？要不要我帮忙理理思路”。 |
| **摸鱼抓包破壁** | 连续在代码/学术状态后，前台突变跃迁至 `gaming`（非免打扰类）或浏览器（B站/视频标签）满 10 分钟。 | 偷瞄工位 $\to$ VLM 识别手里是否拿零食/手机、是否神情放松 $\to$ 抓现行幽默调侃。 |
| **饭点茶歇共鸣** | 时间在 11:45~13:00 或 15:00~16:30，前台非免打扰软件且有间歇输入。 | 偷瞄工位 $\to$ VLM 识别桌面上是否有便当/外卖/奶茶咖啡杯 $\to$ 破壁生活对白。 |
| **深夜修仙守护** | 时间 $> 23:30$ 且前台处于活跃使用（任意分类）。 | 偷瞄工位 $\to$ 识别环境光与困意神态 $\to$ 关照早点休息。 |
| **绝对免打扰熔断** | 前台应用满足 `dnd_inhibit == true`（CS2、Apex、腾讯会议、雨课堂等）。 | **100% 物理拦截**，禁止调用相机拍照，禁止发出任何打扰声音或主动弹出气泡。 |
| **绝对隐私阻断** | 前台应用满足 `visual_safe == false`（微信、QQ、Telegram、ToDesk、PotPlayer）。 | **100% 阻断**任何视觉抓取与 OCR，仅保留最高层级的脱敏状态。 |

---

## 7. 后续落地与集成计划

1. **持久化配置文件交付**：
   - 将完整映射表固化为 `echo_pc_agent/data/software_taxonomy.json`；
2. **PC Agent 代码升级**：
   - 重构 `echo_pc_agent/modules/activity.py`，启动时自动加载 `software_taxonomy.json`，并支持热重载；
   - 补全 Steam 库 `libraryfolders.vdf` 自动动态探测加载器；
3. **单元测试回归**：
   - 为新增的 7 大类映射与免打扰逻辑编写完备的自动化单测，确保 100% 覆盖。
