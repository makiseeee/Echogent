# 网络与安全

## 端口

| 位置 | 端口 | 用途 | 暴露范围 |
|---|---:|---|---|
| 手机 | 6185 | AstrBot WebUI | `127.0.0.1` |
| 手机 | 6199 | OneBot 反向 WebSocket | `127.0.0.1` |
| 手机 | 6099 | NapCat WebUI | `127.0.0.1` |
| 手机 | 8022 | Termux SSH | ZeroTier |
| 电脑 | 8765 | MCP | 手机 ZeroTier IP + Bearer Token |
| 电脑 | 11434 | Ollama | 电脑 ZeroTier 地址，仅允许手机访问 |

## 执行边界

MCP 当前只开放：

- `health_check`
- 受限 `run_python`
- 白名单目录 `read_file`

当前不开放：

- 任意 Shell
- 任意文件写入
- 启动桌面程序
- 系统关机、网络和账户控制

未来增加电脑控制时，应使用明确的程序和参数白名单，而不是通用命令执行。

## 凭据

- SSH 使用专用 ED25519 密钥 `~/.ssh/echo-phone`
- OneBot、MCP、NapCat 和 WebUI Token 只保存在本机私密配置
- `.env`、数据库、备份、QQ 登录数据和私钥不得提交
- 文档只记录配置位置和轮换流程，不记录真实值

## 防火墙

Windows 已配置：

- `8765/tcp` 仅允许手机 `10.144.13.0` 访问
- `11434/tcp` 仅允许手机 `10.144.13.0` 访问

电脑旧 NapCat 容器已经停止。同一机器人 QQ 账号不得同时在电脑和手机 NapCat 登录。

## 数据安全

- 手机是在线主副本，直接复制运行中的 SQLite/WAL 文件可能得到不一致备份
- 修改手机数据库前先停止 `echo-service` 并保留备份
- 插件定制通过 `patches/` 保存，升级插件后需要重新检查补丁是否仍适用
