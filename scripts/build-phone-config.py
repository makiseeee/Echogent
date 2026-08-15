#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the P2 phone AstrBot config")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    config = json.loads(args.source.read_text(encoding="utf-8-sig"))

    config["platform"] = [
        item
        for item in config.get("platform", [])
        if item.get("type") == "webchat"
    ]
    for item in config["platform"]:
        item["enable"] = True

    for provider in config.get("provider", []):
        if provider.get("provider_type") == "embedding":
            provider["enable"] = False

    provider_settings = config.setdefault("provider_settings", {})
    provider_settings["computer_use_runtime"] = "none"

    dashboard = config.setdefault("dashboard", {})
    dashboard["host"] = "127.0.0.1"
    dashboard["port"] = 6185

    config["timezone"] = "Asia/Shanghai"
    config["default_kb_collection"] = ""
    config["kb_names"] = []

    args.output.write_text(
        json.dumps(config, ensure_ascii=False, indent=4) + "\n",
        encoding="utf-8",
    )
    args.output.chmod(0o600)
    print("phone config built")
    print("platforms=webchat")
    print("embedding=disabled")
    print("computer_use_runtime=none")


if __name__ == "__main__":
    main()
