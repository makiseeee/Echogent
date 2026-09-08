"""Live2D 桌面伴侣 HUD 屏幕协同与对白气泡镜像服务 (端口 8099)。"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
from typing import Any

import aiohttp
from core.compat import AstrMessageEvent, logger
from core.http_client import HttpClient


class CompanionHUD:
    """管理与本地 8099 端口 Live2D 屏幕伴侣 HUD 的通讯与状态同步。"""

    HUD_API_URL = "http://127.0.0.1:8099/api/chat/bubble"

    @classmethod
    async def push_bubble(cls, text: str, motion: int = 2) -> None:
        """异步向 MIX 2 屏幕 HUD 服务推送气泡与动作。"""
        clean_text = text.strip()
        if len(clean_text) > 85:
            clean_text = clean_text[:82] + "..."
        try:
            session = await HttpClient.get_session()
            await session.post(
                cls.HUD_API_URL,
                json={"text": clean_text, "motion": motion},
                timeout=aiohttp.ClientTimeout(total=1.0),
            )
        except Exception as exc:
            logger.debug(f"[CompanionHUD] 推送伴侣屏幕气泡失败: {exc}")

    @classmethod
    async def mirror_reply(cls, event: AstrMessageEvent) -> None:
        """全双工跨屏共振：在私聊 QQ 时，伴侣屏幕同步打字与动作。"""
        try:
            res = event.get_result()
            if not res or not hasattr(res, "chain") or not res.chain:
                return

            parts = []
            for comp in res.chain:
                if hasattr(comp, "text") and comp.text:
                    parts.append(str(comp.text))
                elif hasattr(comp, "plain") and comp.plain:
                    parts.append(str(comp.plain))
            full_text = "".join(parts).strip()
            if not full_text:
                return

            if full_text.startswith("🔒") or full_text.startswith("[运行状态]"):
                return

            asyncio.create_task(cls.push_bubble(full_text))
        except Exception as exc:
            logger.debug(f"[CompanionHUD] 跨屏气泡拦截异常: {exc}")

    @classmethod
    def export_companion_tasks(cls, vault_dir: Path | None = None) -> None:
        """从最新日记提取今日待办清单，导出为 Live2D 伴侣屏可读取的 JSON 格式。"""
        try:
            vault = vault_dir or Path(os.environ.get("ECHO_PHONE_VAULT", "/root/obsidiangit"))
            daily_dir = vault / "2. Areas" / "日记"
            if not daily_dir.exists():
                return
            files = sorted(daily_dir.glob("*.md"))
            if not files:
                return
            latest = files[-1]
            content = latest.read_text(encoding="utf-8")
            m = re.search(r"<!-- echo-tasks:start -->(.*?)<!-- echo-tasks:end -->", content, re.DOTALL)
            if not m:
                m2 = re.search(r"## Tasks\s*\n(.*?)(?=\n## |\Z)", content, re.DOTALL)
                raw = m2.group(1) if m2 else ""
            else:
                raw = m.group(1)
            tasks = []
            for line in raw.strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                tm = re.match(r"^- \[( |x|X)\] (.*)$", line)
                if tm:
                    done = tm.group(1).lower() == "x"
                    raw_title = tm.group(2)
                    id_m = re.search(r"id=([a-zA-Z0-9]+)", raw_title)
                    task_id = id_m.group(1) if id_m else ""
                    name = re.sub(r"<!--.*?-->", "", raw_title).strip()
                    tasks.append({"id": task_id, "name": name, "done": done})
            total = len(tasks)
            done_count = sum(1 for t in tasks if t["done"])
            pct = round(done_count / total * 100) if total > 0 else 0
            data = {
                "date": latest.stem,
                "total": total,
                "done": done_count,
                "percent": pct,
                "focus": tasks,
            }
            out_file = Path("/mnt/termux-home/echo_companion/tasks.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[CompanionHUD] 导出桌面待办失败: {exc}")

    @classmethod
    async def export_companion_tasks_async(cls, vault_dir: Path | None = None) -> None:
        """异步非阻塞导出桌面待办清单，避免主事件循环发生磁盘 I/O 阻塞。"""
        await asyncio.to_thread(cls.export_companion_tasks, vault_dir)

