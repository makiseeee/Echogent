# echo 端口收紧 Runbook

> 已归档：本文对应迁移前的电脑端 Docker/NapCat 架构，仅用于追溯。

目的：把当前电脑端的管理端口从 `0.0.0.0` 收紧到本机，降低迁移前暴露面。

当前已备份：

- `backups/echo-backup-20260814-195730.tar.zst`

## 执行结果（2026-08-14）

- AstrBot WebUI：`127.0.0.1:6185`
- NapCat WebUI：`127.0.0.1:6099`
- NapCat 旧 OneBot WebSocket `3001`：不再发布到宿主机
- AstrBot OneBot 反向 WS：`172.17.0.1:6199`，仅 Docker 默认网桥可达
- QQ 反向 WS 已重新连接，AstrBot WebUI 本机访问返回 HTTP 200
- 旧容器保留为 `napcat-before-port-hardening`，已停止并设置 `restart=no`

## 1. 收紧 AstrBot WebUI

修改 `astrbot/data/cmd_config.json`：

- `dashboard.host`: `0.0.0.0` -> `127.0.0.1`
- `dashboard.port`: 保持 `6185`

重启：

```bash
systemctl --user restart astrbot.service
```

验证：

```bash
systemctl --user is-active astrbot.service
ss -lntp | grep 6185
curl -s -m 3 http://127.0.0.1:6185 >/dev/null && echo ok
```

预期：

- AstrBot 仍是 `active`
- `6185` 只监听 `127.0.0.1`

回滚：

```bash
cp astrbot/data/cmd_config.json.bak-PORT-HARDEN astrbot/data/cmd_config.json
systemctl --user restart astrbot.service
```

## 2. 收紧 NapCat Docker 端口

当前容器：

- image: `dockerproxy.net/mlikiowa/napcat-docker:latest`
- restart policy: `always`
- volumes:
  - `napcat_config:/app/napcat/config`
  - `napcat_qq:/root/.config/QQ`
  - anonymous volume: `/app/.config/QQ`
  - bind mount: `/tmp/openclaw-onebot:/tmp/openclaw-onebot`

因为 Docker 不能原地修改端口映射，需要重建容器。

先记录匿名 volume 名：

```bash
docker inspect napcat --format '{{range .Mounts}}{{if eq .Destination "/app/.config/QQ"}}{{.Name}}{{end}}{{end}}'
```

停止并重建：

```bash
docker stop napcat
docker rename napcat napcat-before-port-hardening

docker run -d \
  --name napcat \
  --restart always \
  -e WS_ENABLE=true \
  -e NAPCAT_UID=0 \
  -e NAPCAT_GID=0 \
  -e ACCOUNT="$NAPCAT_ACCOUNT" \
  -e NAPCAT_QUICK_PASSWORD="$NAPCAT_QUICK_PASSWORD" \
  -p 127.0.0.1:6099:6099 \
  -v napcat_config:/app/napcat/config \
  -v napcat_qq:/root/.config/QQ \
  -v "$NAPCAT_APP_QQ_VOLUME":/app/.config/QQ \
  -v /tmp/openclaw-onebot:/tmp/openclaw-onebot \
  dockerproxy.net/mlikiowa/napcat-docker:latest
```

注意：

- `$NAPCAT_ACCOUNT` 和 `$NAPCAT_QUICK_PASSWORD` 不要写进仓库
- `$NAPCAT_APP_QQ_VOLUME` 使用上一步查到的匿名 volume 名
- OpenClaw 已停用，因此旧 OneBot WebSocket `3001` 不再发布；需要时再显式加回
- 确认新容器可用后，再删除 `napcat-before-port-hardening`

验证：

```bash
docker ps --filter name=napcat --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -lntp | grep -E '6099|3001'
```

预期：

- `6099` 和 `3001` 只绑定 `127.0.0.1`
- QQ 私聊 echo 仍能收到回复

回滚：

```bash
docker stop napcat
docker rm napcat
docker rename napcat-before-port-hardening napcat
docker start napcat
```

## 3. OneBot 反向 WS 已绑定 Docker 网桥

当前 NapCat 通过 Docker 默认网桥网关 `172.17.0.1` 连接 AstrBot。

已将 `ws_reverse_host` 从 `0.0.0.0` 改为 `172.17.0.1`，因此局域网不再能直接访问 `6199`。

验证：

```bash
ss -lntp | grep 6199
ss -tnp | grep 6199
```

预期：

- 只监听 `172.17.0.1:6199`
- 存在来自 NapCat 容器地址的已建立连接

回滚：

```bash
cp astrbot/data/cmd_config.json.bak-PORT-HARDEN astrbot/data/cmd_config.json
systemctl --user restart astrbot.service
```

## 4. MCP 执行端仅监听本机

当前 `echo-executor` 在 WSL mirrored 网络监听 `0.0.0.0:8765`，使用 Bearer Token 鉴权；
Windows 防火墙只允许手机 ZeroTier 地址访问该端口；
AstrBot 的裸机执行已关闭，coder 只能调用三个低风险 MCP 工具和计算器。

验证：

```bash
systemctl --user is-active echo-mcp.service
systemctl --user is-enabled echo-mcp.service
ss -lntp | grep 8765
curl -i --max-time 3 http://127.0.0.1:8765/mcp
```

预期未携带 Token 的请求返回 HTTP 401，且端口只显示 `127.0.0.1:8765`。

重装或更新：

```bash
bash scripts/install-mcp-local.sh
```

回滚：停止并禁用 `echo-mcp.service`，从
`astrbot/data/mcp_server.json` 移除 `echo-executor` 后重启 AstrBot。
