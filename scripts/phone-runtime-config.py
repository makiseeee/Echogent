#!/usr/bin/env python3
"""Apply non-secret runtime defaults to the phone AstrBot config."""

import json
import os
from pathlib import Path


def load_secret(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value

    secret_path = Path("/mnt/termux-home/.echo-secrets")
    if not secret_path.is_file():
        return ""
    for raw_line in secret_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, raw_value = line.partition("=")
        if separator and key.strip() == name:
            return raw_value.strip().strip("'\"")
    return ""


path = Path(os.environ.get("ECHO_PHONE_CONFIG", "/opt/echo/data/cmd_config.json"))
config = json.loads(path.read_text(encoding="utf-8-sig"))

config["default_kb_collection"] = ""
config["kb_names"] = []
config["kb_agentic_mode"] = False

provider_settings = config.setdefault("provider_settings", {})
provider_settings["max_context_length"] = 8  # 精简到 8 轮，降低单次 token 开销
provider_settings["context_limit_reached_strategy"] = "llm_compress"
provider_settings["request_max_retries"] = 2  # 关键：避免失败时重试卡顿 15s

hajimi_key = load_secret("ECHO_HAJIMI_API_KEY")
sources = config.setdefault("provider_sources", [])
source = next((item for item in sources if item.get("id") in {"hajimi_responses_source", "hajimi_source"}), None)
existing_keys = list((source or {}).get("key") or [])
source_config = {
    "id": "hajimi_source",
    "provider": "openai",
    "type": "openai_chat_completion",
    "provider_type": "chat_completion",
    "key": [hajimi_key] if hajimi_key else existing_keys,
    "api_base": "https://api.hajimi.chat/v1",
    "timeout": 120,
    "proxy": "",
    "custom_headers": {},
}
if source is None:
    if not source_config["key"]:
        raise SystemExit("ECHO_HAJIMI_API_KEY is required for initial Hajimi setup")
    sources.append(source_config)
else:
    source.clear()
    source.update(source_config)

providers = config.setdefault("provider", [])

# 1. 0元永久免费主力模型：智谱 GLM-4-Flash (1.0s 极速秒回，工具完美，¥0.00)
glm_flash = next((item for item in providers if item.get("id") == "glm_flash"), None)
glm_flash_config = {
    "id": "glm_flash",
    "enable": True,
    "model": "glm-4-flash",
    "provider_source_id": "zhipu_source",
    "modalities": [],
    "custom_extra_body": {},
}
if glm_flash is None:
    providers.insert(0, glm_flash_config)
else:
    glm_flash.clear()
    glm_flash.update(glm_flash_config)

# 2. 备用容灾模型：硅基流动 DeepSeek-V4-Flash
sf_v4 = next((item for item in providers if item.get("id") == "siliconflow_deepseek_v4_flash"), None)
sf_v4_config = {
    "id": "siliconflow_deepseek_v4_flash",
    "enable": True,
    "model": "deepseek-ai/DeepSeek-V4-Flash",
    "provider_source_id": "siliconflow_source",
    "modalities": [],
    "custom_extra_body": {
        "enable_thinking": False
    },
}
if sf_v4 is None:
    providers.insert(1, sf_v4_config)
else:
    sf_v4.clear()
    sf_v4.update(sf_v4_config)

# 3. 备用平价模型：Qwen2.5-72B
sf_qwen = next((item for item in providers if item.get("id") == "sf_qwen_72b"), None)
sf_qwen_config = {
    "id": "sf_qwen_72b",
    "enable": True,
    "model": "Qwen/Qwen2.5-72B-Instruct",
    "provider_source_id": "siliconflow_source",
    "modalities": [],
    "custom_extra_body": {},
}
if sf_qwen is None:
    providers.insert(2, sf_qwen_config)
else:
    sf_qwen.clear()
    sf_qwen.update(sf_qwen_config)

provider_settings["default_provider_id"] = "siliconflow_deepseek_v4_flash"
provider_settings["fallback_chat_models"] = ["sf_qwen_72b", "glm_flash"]

path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
path.chmod(0o600)
