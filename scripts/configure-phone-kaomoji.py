#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path


CONFIG = Path("/opt/echo/data/config/astrbot_plugin_meme_manager_lite_config.json")
BACKUP = CONFIG.with_suffix(".json.bak-kaomoji")

if not BACKUP.exists():
    shutil.copy2(CONFIG, BACKUP)

config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
config["sticker_mode"] = "kaomoji"
CONFIG.write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
CONFIG.chmod(0o600)
print("sticker_mode=kaomoji")
print(f"backup={BACKUP}")
