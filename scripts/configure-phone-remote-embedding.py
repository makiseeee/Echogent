#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from pathlib import Path


CONFIG = Path("/opt/echo/data/cmd_config.json")
BACKUP = CONFIG.with_suffix(".json.bak-remote-embedding")
EMBEDDING_BASE = "http://10.144.232.236:11434"


config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
if not BACKUP.exists():
    shutil.copy2(CONFIG, BACKUP)

providers = config.setdefault("provider", [])
embedding = next(
    (item for item in providers if item.get("id") == "ollama_embedding"),
    None,
)
if embedding is None:
    embedding = {"id": "ollama_embedding", "type": "ollama_embedding"}
    providers.append(embedding)

embedding.update(
    {
        "provider": "ollama",
        "provider_type": "embedding",
        "enable": True,
        "embedding_api_base": EMBEDDING_BASE,
        "embedding_model": "bge-m3",
        "embedding_dimensions": 1024,
        "timeout": 60,
        "proxy": "",
    }
)

CONFIG.write_text(
    json.dumps(config, ensure_ascii=False, indent=4) + "\n",
    encoding="utf-8",
)
CONFIG.chmod(0o600)
print(f"remote embedding enabled: {EMBEDDING_BASE}")
print(f"backup={BACKUP}")
