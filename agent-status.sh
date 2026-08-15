#!/usr/bin/env bash
# 一键查看 echo 的运行状态（AstrBot + Ollama + NapCat + 备份）

echo "=== AstrBot ==="
systemctl --user is-active astrbot.service 2>/dev/null || echo "未运行"

echo "=== Ollama（本地嵌入）==="
systemctl --user is-active ollama.service 2>/dev/null || echo "未运行"
curl -s -m 3 http://127.0.0.1:11434/api/tags 2>/dev/null | python3 -c \
  "import json,sys; d=json.load(sys.stdin); print('models:', [m['name'] for m in d.get('models',[])])" \
  2>/dev/null || echo "Ollama API 不可达"

echo "=== MCP 执行端 ==="
systemctl --user is-active echo-mcp.service 2>/dev/null || echo "未运行"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -m 3 http://127.0.0.1:8765/mcp \
  2>/dev/null || echo "MCP 端点不可达"

echo "=== NapCat (QQ) ==="
docker ps --filter name=napcat --format '{{.Status}} | {{.Ports}}' 2>/dev/null || echo "Docker 不可用"

echo "=== 备份 ==="
ls -lht backups/ 2>/dev/null | head -4

echo
echo "提示：QQ 发消息给 echo 看有没有回复，是最直接的验证。"
