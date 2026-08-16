#!/usr/bin/env python3
import json
import secrets
import shutil
from pathlib import Path


ASTRBOT_CONFIG = Path("/opt/echo/data/cmd_config.json")
NAPCAT_CONFIG = Path(
    "/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/"
    "onebot11_1812441617.json"
)
TOKEN_FILE = Path("/root/.echo-onebot-token")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def backup(path: Path) -> None:
    backup_path = path.with_suffix(path.suffix + ".bak-phone-onebot")
    if not backup_path.exists():
        shutil.copy2(path, backup_path)


token = secrets.token_urlsafe(48)

astrbot = load(ASTRBOT_CONFIG)
backup(ASTRBOT_CONFIG)
platforms = [item for item in astrbot.get("platform", []) if item.get("id") != "echo-qq"]
platforms.insert(
    0,
    {
        "id": "echo-qq",
        "type": "aiocqhttp",
        "enable": True,
        "ws_reverse_host": "127.0.0.1",
        "ws_reverse_port": 6199,
        "ws_reverse_token": token,
    },
)
astrbot["platform"] = platforms
save(ASTRBOT_CONFIG, astrbot)

napcat = load(NAPCAT_CONFIG)
backup(NAPCAT_CONFIG)
network = napcat.setdefault("network", {})
clients = [item for item in network.get("websocketClients", []) if item.get("name") != "astrbot-ws"]
clients.append(
    {
        "enable": True,
        "name": "astrbot-ws",
        "url": "ws://127.0.0.1:6199/ws",
        "reportSelfMessage": False,
        "messagePostFormat": "array",
        "token": token,
        "debug": False,
        "heartInterval": 30000,
        "reconnectInterval": 3000,
    }
)
network["websocketClients"] = clients
save(NAPCAT_CONFIG, napcat)

TOKEN_FILE.write_text(token + "\n", encoding="utf-8")
TOKEN_FILE.chmod(0o600)
print("phone OneBot configuration updated")
