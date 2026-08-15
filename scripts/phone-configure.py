#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path


CONFIG = Path("/opt/echo/data/cmd_config.json")
BACKUP = CONFIG.with_suffix(".json.bak-P2")

if not CONFIG.is_file():
    raise SystemExit(f"missing config: {CONFIG}")

if not BACKUP.exists():
    shutil.copy2(CONFIG, BACKUP)

config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
dashboard = config.setdefault("dashboard", {})
dashboard["host"] = "127.0.0.1"
dashboard["port"] = 6185

provider_settings = config.setdefault("provider_settings", {})
provider_settings["computer_use_runtime"] = "none"

CONFIG.write_text(
    json.dumps(config, ensure_ascii=False, indent=4) + "\n",
    encoding="utf-8",
)
CONFIG.chmod(0o600)

print("dashboard=127.0.0.1:6185")
print("computer_use_runtime=none")
print(f"backup={BACKUP}")
