#!/usr/bin/env bash
# 安装本机 MCP 服务并合并 AstrBot 私密配置；不会覆盖其他 MCP server。
set -euo pipefail

WORKSPACE_ROOT="/home/wenbo/aaage"
EXECUTOR_DIR="$WORKSPACE_ROOT/mcp-executor"
ENV_FILE="$EXECUTOR_DIR/.env"
MCP_CONFIG="$WORKSPACE_ROOT/astrbot/data/mcp_server.json"
UNIT_SOURCE="$WORKSPACE_ROOT/systemd/echo-mcp.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_TARGET="$UNIT_DIR/echo-mcp.service"
ASTRBOT_PYTHON="/home/wenbo/.local/share/uv/tools/astrbot/bin/python3"

mkdir -p "$EXECUTOR_DIR/workspace" "$UNIT_DIR"

if [ ! -s "$ENV_FILE" ]; then
  "$ASTRBOT_PYTHON" - "$ENV_FILE" <<'PY'
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
token = secrets.token_urlsafe(48)
path.write_text(
    "ECHO_MCP_HOST=127.0.0.1\n"
    "ECHO_MCP_PORT=8765\n"
    f"ECHO_MCP_TOKEN={token}\n"
    f"ECHO_MCP_ALLOWED_ROOTS={path.parent / 'workspace'}\n",
    encoding="utf-8",
)
path.chmod(0o600)
PY
fi

"$ASTRBOT_PYTHON" - "$ENV_FILE" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
defaults = {
    "ECHO_OBSIDIAN_VAULT": "/mnt/d/wenboo",
    "ECHO_OBSIDIAN_OWNER_ID": "1249403130",
    "ECHO_OBSIDIAN_GIT_ENABLED": "false",
    "ECHO_OBSIDIAN_GIT_REMOTE": "gitee",
    "ECHO_OBSIDIAN_GIT_BRANCH": "main",
    "ECHO_OBSIDIAN_GIT_TIMEOUT": "30",
    "ECHO_OBSIDIAN_GIT_USERNAME": "Weeenbo",
}
present = {line.split("=", 1)[0] for line in text.splitlines() if "=" in line}
for key, value in defaults.items():
    if key not in present:
        text += f"{key}={value}\n"
path.write_text(text, encoding="utf-8")
path.chmod(0o600)
PY

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"

"$ASTRBOT_PYTHON" - "$ENV_FILE" "$MCP_CONFIG" <<'PY'
import json
import sys
from pathlib import Path

env_path, config_path = map(Path, sys.argv[1:])
env = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        env[key] = value

token = env["ECHO_MCP_TOKEN"]
port = int(env.get("ECHO_MCP_PORT", "8765"))
if config_path.exists():
    config = json.loads(config_path.read_text(encoding="utf-8"))
else:
    config = {"mcpServers": {}}
servers = config.setdefault("mcpServers", {})
servers["echo-executor"] = {
    "url": f"http://127.0.0.1:{port}/mcp",
    "transport": "streamable_http",
    "headers": {"Authorization": f"Bearer {token}"},
    "timeout": 5,
    "sse_read_timeout": 60,
    "session_read_timeout": 15,
    "active": True,
}
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
config_path.chmod(0o600)
PY

systemctl --user daemon-reload
systemctl --user enable --now echo-mcp.service
systemctl --user restart astrbot.service

echo "echo MCP installed: http://127.0.0.1:8765/mcp"
