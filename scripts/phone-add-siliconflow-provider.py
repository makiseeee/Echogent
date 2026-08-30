#!/usr/bin/env python3
"""Add SiliconFlow DeepSeek as primary while retaining GLM fallback."""

from __future__ import annotations

import json
import os
from pathlib import Path


path = Path(os.environ.get("ECHO_PHONE_CONFIG", "/opt/echo/data/cmd_config.json"))
api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
if not api_key:
    raise SystemExit("SILICONFLOW_API_KEY is required")

data = json.loads(path.read_text(encoding="utf-8"))
sources = data.setdefault("provider_sources", [])
source = next((item for item in sources if item.get("id") == "siliconflow_source"), None)
source_config = {
    "id": "siliconflow_source",
    "provider": "siliconflow",
    "type": "openai_chat_completion",
    "provider_type": "chat_completion",
    "key": [api_key],
    "api_base": "https://api.siliconflow.cn/v1",
    "timeout": 120,
    "proxy": "",
    "custom_headers": {},
}
if source is None:
    sources.append(source_config)
else:
    source.clear()
    source.update(source_config)

providers = data.setdefault("provider", [])
provider = next((item for item in providers if item.get("id") == "siliconflow_deepseek_v4_flash"), None)
provider_config = {
    "id": "siliconflow_deepseek_v4_flash",
    "enable": True,
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "provider_source_id": "siliconflow_source",
    "modalities": [],
    # DeepSeek V4 Flash: keep ordinary QQ chat fast and concise.
    # Tool calls remain available; this only disables the model's visible/extended
    # reasoning mode for the default provider.
    "custom_extra_body": {"enable_thinking": False},
}
if provider is None:
    providers.insert(0, provider_config)
else:
    provider.clear()
    provider.update(provider_config)

settings = data.setdefault("provider_settings", {})
settings["default_provider_id"] = "siliconflow_deepseek_v4_flash"
fallback = [item for item in settings.get("fallback_chat_models", []) if item != "glm_flash"]
settings["fallback_chat_models"] = ["glm_flash", *fallback]

path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
