"""echo 工具集：免费 Bing 联网搜索 + 网页抓取 + 安全计算器。"""

import ast
import asyncio
import functools
import json
import math
import os
import shutil
from pathlib import Path
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
import time
from typing import Any

_plugin_dir = str(Path(__file__).resolve().parent)
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

import aiohttp
from lxml import html as lxml_html

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, register
try:
    from astrbot.core.provider.entities import TextPart
except ImportError:  # AstrBot 4.27.x compatibility
    TextPart = None

try:
    from daily_task_manager import DailyTaskManager, TaskAmbiguityError
    from obsidian_git import VaultGitSync
    from obsidian_access import AccessMode, VaultAccessPolicy
    from obsidian_search import list_notes, read_note_excerpt, search_vault
    from obsidian_write import NoteWriteService
except Exception as e:
    logger.exception(f"[EchoTools] Failed to import daily/obsidian modules: {e}")
    DailyTaskManager = None
    TaskAmbiguityError = ValueError
    VaultGitSync = None
    AccessMode = VaultAccessPolicy = NoteWriteService = None


@register("echo-tools", "echo", "DuckDuckGo 搜索 + 安全计算器", "1.0.0")
class EchoTools(Star):
    _DAILY_CRON_SPECS = (
        {
            "name": "EchoDaily_MorningDispatch",
            "cron_expression": "30 8 * * *",
            "description": "Echo 每日晨间任务出库与晨报",
            "note": (
                "【每日晨间任务调度】这是固定晨报任务。先调用 daily_dispatch 获取今日真实任务，"
                "再根据 DDL、轻重和数量自然安排先后顺序，严禁机械套用固定时段。"
                "【自动挂载定时提醒】检查今日已出库任务（包含一次性待办与循环习惯）中是否有带具体时分（如 20:00、15:30 等）的任务；"
                "若该时间在今天尚未到来，计算距离当前时刻的分钟数，调用 schedule_wakeup(delay_minutes, future_prompt) 为其自动挂载今日的定时私聊提醒！"
                "有硬截止任务时优先说明；任务很少时保持精炼。询问 wenbo 昨晚睡眠和今天精力，"
                "说明可随时调整或削减任务。日常称呼使用 wenbo。最后必须调用 send_message_to_user，"
                "向当前 QQ 私聊发送简短晨报。"
            ),
        },
        {
            "name": "EchoDaily_EveningRecap",
            "cron_expression": "20 23 * * *",
            "description": "Echo 每日晚间复盘问询与超时回流",
            "note": (
                "【每日晚间复盘报告】这是每天 23:20 发给 wenbo 的专属晚间总结。你的核心职责是复盘今日任务完成度与灵感收获，向 wenbo 发送一条温暖且傲娇的晚间总结。日常称呼必须且只能使用五个小写英文字母 wenbo。严禁输出任何系统 Emoji（如 ✨、😊、🎉 等）。\\n【必须严格遵守的纪律】\\n1. 这是正式的【日终复盘】，严禁写成催促超时的赌气追问（严禁说“半天没动静/当我没说过/账我不记/随你”之类赌气生硬的话）！\\n2. 唯一事实标准：调用 obsidian_read(path='2. Areas/日记/YYYY-MM-DD.md') 读取今日日记。日记里 ## Tasks 下的勾选框（- [x] 为已完成，- [ ] 为未完成）是今日进度的唯一绝对事实！只要日记里打了勾即代表已完成，严禁怀疑！读取一次即可，严禁调用 daily_list_inventory 或 daily_recap，严禁重复调用 obsidian 工具！\\n3. 【排版与分段绝对规范】晚报必须层次分明，每个部分之间必须留出空行（使用 \\n\\n 换行）清晰分段，绝对禁止挤成密不透风的一大坨话！按以下三个段落组织：\\n   - 【第一段·任务盘点】：傲娇地盘点搞定的任务（如见导师、学籍注册、读书、日记等）；如果全部打勾，要别扭地肯定与夸奖（如“今天居然把待办全清空了，算你没偷懒，还挺利索的”）；若有未完成才提醒早点休息；\\n   - 【第二段·灵感与碎碎念共鸣】：日记的 ## Thino 里有 wenbo 记录的灵感思考（比如今天关于可乐奖励、GAN/Diffusion生成与自由意志的哲学发散），务必提取出来认真共鸣、聊上两句；\\n   - 【第三段·晚安道别】：提醒早点休息，晚安。\\n4. 组织好后，调用 send_message_to_user 发送到 QQ 私聊，然后调用 schedule_wakeup(delay_minutes=40, future_prompt='40分钟超时回流检查') 设定深夜超时兜底。"
            ),
        },
    )

    def __init__(self, context: Context):
        super().__init__(context)
        self._obsidian_pending: dict[str, str] = {}
        self._obsidian_link_pending: dict[str, str] = {}
        self._computer_online = False
        self._computer_detail = ""
        self._pc_activity: dict[str, Any] = {}
        self._computer_prober_task = None
        self._battery_monitor_task = None
        self._mind_arbiter_task = None
        self._last_charging_state: bool | None = None
        self._last_proactive_ts: float = 0.0
        self._gaming_alerted_key: str | None = None
        self._focus_alerted_key: str | None = None
        self._battery_low_alerted = False
        self._battery_critical_alerted = False
        self._daily_manager = None
        self._obsidian_local = None
        self._export_companion_tasks()
        try:
            self._computer_prober_task = asyncio.create_task(self._background_computer_prober())
        except RuntimeError:
            # AstrBot may construct stars before the event loop is running.
            self._computer_prober_task = None
        data_root = Path(os.environ.get("ECHO_ASTRBOT_DATA", "data"))
        data_root.mkdir(parents=True, exist_ok=True)
        self._usage_db = data_root / "echo-tools-token-usage.db"
        with sqlite3.connect(self._usage_db) as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS usage (
                    id INTEGER PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    chat_type TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_other INTEGER NOT NULL,
                    input_cached INTEGER NOT NULL,
                    output INTEGER NOT NULL,
                    total INTEGER NOT NULL,
                    estimated_cost_cny REAL NOT NULL,
                    estimated_cost_usd REAL NOT NULL DEFAULT 0.0
                )
            """)
            cols = [r[1] for r in db.execute("PRAGMA table_info(usage)").fetchall()]
            if "estimated_cost_usd" not in cols:
                db.execute("ALTER TABLE usage ADD COLUMN estimated_cost_usd REAL NOT NULL DEFAULT 0.0")
        self._patch_openai_token_interceptor()

    @classmethod
    def _usage_db_path(cls) -> Path:
        data_root = Path(os.environ.get("ECHO_ASTRBOT_DATA", "data"))
        return data_root / "echo-tools-token-usage.db"

    @classmethod
    def _patch_openai_token_interceptor(cls) -> None:
        if getattr(cls, "_openai_token_patched", False):
            return
        try:
            from openai.resources.chat.completions import AsyncCompletions

            orig_create = AsyncCompletions.create
            db_path = cls._usage_db_path()

            @functools.wraps(orig_create)
            async def wrapped_create(*args, **kwargs):
                is_stream = kwargs.get("stream", False)
                resp = await orig_create(*args, **kwargs)
                if not is_stream:
                    cls._record_api_usage(db_path, resp)
                    return resp
                else:
                    async def wrapped_stream():
                        captured = False
                        async for chunk in resp:
                            if not captured and hasattr(chunk, "usage") and chunk.usage:
                                u = chunk.usage
                                p_tok = getattr(u, "prompt_tokens", 0) or 0
                                c_tok = getattr(u, "completion_tokens", 0) or 0
                                if p_tok > 0 or c_tok > 0:
                                    cls._record_api_usage(db_path, chunk)
                                    captured = True
                            yield chunk
                    return wrapped_stream()

            AsyncCompletions.create = wrapped_create
            cls._openai_token_patched = True
            logger.info("[EchoTools] 全局 OpenAI/SiliconFlow API Token 拦截器挂载成功。")
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[EchoTools] 挂载全局 Token 拦截器失败: {exc}")

    @classmethod
    def _record_api_usage(cls, db_path: Path, completion_obj: Any) -> None:
        try:
            usage = getattr(completion_obj, "usage", None)
            if not usage:
                return
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            if prompt_tokens == 0 and completion_tokens == 0:
                return

            ptd = getattr(usage, "prompt_tokens_details", None)
            cached = 0
            if ptd:
                if isinstance(ptd, dict):
                    cached = int(ptd.get("cached_tokens", 0) or 0)
                else:
                    cached = int(getattr(ptd, "cached_tokens", 0) or getattr(ptd, "cached_prompt_tokens", 0) or 0)

            input_cached = cached
            input_other = max(0, prompt_tokens - cached)
            output = completion_tokens
            total = input_other + input_cached + output
            model = str(getattr(completion_obj, "model", "") or "unknown")
            cost_usd = cls._estimate_cost(model, input_other, input_cached, output)
            cost_cny = cost_usd * 7.2

            with sqlite3.connect(db_path, timeout=10.0) as db:
                db.execute(
                    "INSERT INTO usage(created_at,user_id,chat_type,model,input_other,input_cached,output,total,estimated_cost_cny,estimated_cost_usd) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        "global",
                        "api",
                        model,
                        input_other,
                        input_cached,
                        output,
                        total,
                        cost_cny,
                        cost_usd,
                    ),
                )
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EchoTools] 记录 Token 用量失败: {e}")

    @classmethod
    def _auto_compile_persona(cls) -> None:
        try:
            from datetime import datetime, timezone
            root_candidates = [Path("/opt/echo"), Path("/home/wenbo/aaage"), Path.cwd()]
            root_dir = next((c for c in root_candidates if (c / "SOUL.md").exists() and (c / "USER.md").exists()), None)
            if not root_dir:
                return
            
            parts = []
            for fname in ("SOUL.md", "USER.md", "RELATIONSHIP.md"):
                fpath = root_dir / fname
                if fpath.exists():
                    lines = [l for l in fpath.read_text(encoding="utf-8").strip().splitlines() if not re.match(r"^#\s+[A-Z_]+\.md", l)]
                    parts.append("\n".join(lines).strip())
            
            compiled = "\n\n".join(p for p in parts if p).strip()
            if not compiled:
                return
            
            # Update target md
            target_md = root_dir / "astrbot" / "echo-persona.md"
            if not target_md.parent.exists():
                target_md = root_dir / "echo-persona.md"
            target_md.write_text(compiled, encoding="utf-8")
            
            # Sync to data_v4.db
            db_candidates = [root_dir / "data" / "data_v4.db", root_dir / "astrbot" / "data" / "data_v4.db", Path("/opt/echo/data/data_v4.db")]
            for db_path in db_candidates:
                if db_path.exists():
                    with sqlite3.connect(db_path, timeout=5.0) as con:
                        cur = con.cursor()
                        now_str = datetime.now(timezone.utc).isoformat()
                        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                        if "personas" in tables:
                            row = cur.execute("SELECT id FROM personas WHERE persona_id = 'echo'").fetchone()
                            if row:
                                cur.execute("UPDATE personas SET system_prompt = ?, updated_at = ? WHERE persona_id = 'echo'", (compiled, now_str))
                            else:
                                cur.execute("INSERT INTO personas (created_at, updated_at, persona_id, system_prompt, begin_dialogs, sort_order) VALUES (?, ?, 'echo', ?, '[]', 0)", (now_str, now_str, compiled))
                            con.commit()
            logger.info("[EchoTools] 自适应人格编译器执行完成，已自动同步最新 SOUL/USER/RELATIONSHIP 人设。")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[EchoTools] 自动编译人格失败: {exc}")

    async def initialize(self) -> None:
        self._auto_compile_persona()
        if self._computer_prober_task is None or self._computer_prober_task.done():
            self._computer_prober_task = asyncio.create_task(self._background_computer_prober())
        if self._battery_monitor_task is None or self._battery_monitor_task.done():
            self._battery_monitor_task = asyncio.create_task(self._background_battery_monitor())
        if self._mind_arbiter_task is None or self._mind_arbiter_task.done():
            self._mind_arbiter_task = asyncio.create_task(self._background_mind_arbiter())
        try:
            await self._ensure_daily_cron_jobs()
        except Exception:  # noqa: BLE001
            logger.exception("[EchoTools] failed to register daily cron jobs")

    async def terminate(self) -> None:
        if self._computer_prober_task is not None:
            self._computer_prober_task.cancel()
            try:
                await self._computer_prober_task
            except asyncio.CancelledError:
                pass
            self._computer_prober_task = None
        if self._battery_monitor_task is not None:
            self._battery_monitor_task.cancel()
            try:
                await self._battery_monitor_task
            except asyncio.CancelledError:
                pass
            self._battery_monitor_task = None
        if self._mind_arbiter_task is not None:
            self._mind_arbiter_task.cancel()
            try:
                await self._mind_arbiter_task
            except asyncio.CancelledError:
                pass
            self._mind_arbiter_task = None

    @classmethod
    def _daily_cron_session(cls) -> str:
        configured = os.environ.get("ECHO_DAILY_SESSION", "").strip()
        if configured:
            return configured

        owner_ids = cls._owner_ids()
        try:
            db_path = cls._data_file("data_v4.db")
            with sqlite3.connect(db_path) as db:
                for owner_id in owner_ids:
                    row = db.execute(
                        "SELECT user_id FROM conversations "
                        "WHERE user_id LIKE ? ORDER BY updated_at DESC LIMIT 1",
                        (f"%:FriendMessage:{owner_id}",),
                    ).fetchone()
                    if row and row[0]:
                        return str(row[0])
        except (OSError, sqlite3.Error):
            logger.warning("[EchoTools] could not resolve daily cron session from conversations")

        if len(owner_ids) == 1:
            return f"echo-qq:FriendMessage:{next(iter(owner_ids))}"
        raise RuntimeError("无法确定每日自动任务的 QQ 私聊会话，请设置 ECHO_DAILY_SESSION")

    async def _ensure_daily_cron_jobs(self) -> None:
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            raise RuntimeError("AstrBot Cron 服务不可用")

        session = self._daily_cron_session()
        sender_id = session.rsplit(":", 1)[-1]
        jobs = await cron_manager.list_jobs(job_type="active_agent")

        for spec in self._DAILY_CRON_SPECS:
            matching = [job for job in jobs if job.name == spec["name"]]
            payload = {
                "session": session,
                "sender_id": sender_id,
                "note": spec["note"],
                "origin": "echo-tools",
            }
            if matching:
                current = matching[0]
                if (
                    current.cron_expression != spec["cron_expression"]
                    or current.timezone != "Asia/Shanghai"
                    or current.payload != payload
                    or current.description != spec["description"]
                    or not current.enabled
                    or not current.persistent
                    or current.run_once
                ):
                    await cron_manager.update_job(
                        current.job_id,
                        cron_expression=spec["cron_expression"],
                        timezone="Asia/Shanghai",
                        payload=payload,
                        description=spec["description"],
                        enabled=True,
                        persistent=True,
                        run_once=False,
                    )
                for duplicate in matching[1:]:
                    await cron_manager.delete_job(duplicate.job_id)
            else:
                await cron_manager.add_active_job(
                    name=spec["name"],
                    cron_expression=spec["cron_expression"],
                    payload=payload,
                    description=spec["description"],
                    timezone="Asia/Shanghai",
                    enabled=True,
                    persistent=True,
                    run_once=False,
                )

    @staticmethod
    def _estimate_cost(model: str, input_other: int, input_cached: int, output: int, created_at: datetime | None = None) -> float:
        """
        按 Command Code 官方 Go 计划费率计算美元成本（USD）。
        参考文档: https://commandcode.ai/docs/plans/go (单位: $ / 1M tokens)
        """
        normalized = model.lower()
        now_dt = created_at or datetime.now(timezone.utc)
        utc_hour = now_dt.hour
        # Command Code 峰值时段: 01:00-04:00 & 06:00-10:00 UTC (每日共 7 小时)
        is_peak = (1 <= utc_hour < 4) or (6 <= utc_hour < 10)

        # 1. DeepSeek V4 Flash Fast (当前主力，固定阶梯，无高峰期溢价)
        # Input: $0.28/M, Output: $0.56/M, CacheRead: $0.07/M
        if "flash-fast" in normalized or "flash_fast" in normalized:
            rate_in, rate_cached, rate_out = 0.28, 0.07, 0.56

        # 2. DeepSeek V4 Flash / Vision (标准版，分高峰/平峰)
        # Off-peak: In $0.22/M, Out $0.66/M, Cache $0.007/M
        # Peak:     In $0.44/M, Out $1.32/M, Cache $0.014/M
        elif "v4-flash" in normalized or "v4_flash" in normalized or ("deepseek-v4" in normalized and "pro" not in normalized):
            if is_peak:
                rate_in, rate_cached, rate_out = 0.44, 0.014, 1.32
            else:
                rate_in, rate_cached, rate_out = 0.22, 0.007, 0.66

        # 3. DeepSeek V4 Pro (分高峰/平峰)
        # Off-peak: In $0.66/M, Out $1.98/M, Cache $0.022/M
        # Peak:     In $1.32/M, Out $3.96/M, Cache $0.044/M
        elif "v4-pro" in normalized or "v4_pro" in normalized:
            if is_peak:
                rate_in, rate_cached, rate_out = 1.32, 0.044, 3.96
            else:
                rate_in, rate_cached, rate_out = 0.66, 0.022, 1.98

        # 4. 其他通用 DeepSeek (V3 / R1 等)
        elif "deepseek" in normalized:
            rate_in, rate_cached, rate_out = 0.28, 0.07, 0.56

        # 5. GLM 系列 (智谱 / Z-AI)
        # GLM-5.3 Flash: In $0.15/M, Out $0.50/M, Cache $0.03/M
        elif "glm-5.3-flash" in normalized or ("glm-5" in normalized and "flash" in normalized):
            rate_in, rate_cached, rate_out = 0.15, 0.03, 0.50
        elif "glm-4" in normalized:
            rate_in, rate_cached, rate_out = 0.10, 0.02, 0.10
        elif "glm" in normalized:
            rate_in, rate_cached, rate_out = 1.40, 0.26, 4.40

        # 6. Qwen 系列
        # Qwen 3.8 Flash: In $0.16/M, Out $0.47/M, Cache $0.016/M
        # Qwen 3.8 27B:   In $0.40/M, Out $3.00/M, Cache $0.04/M
        # Qwen 3.8 Max:   In $2.00/M, Out $6.00/M, Cache $0.25/M
        elif "qwen" in normalized and "flash" in normalized:
            rate_in, rate_cached, rate_out = 0.16, 0.016, 0.47
        elif "qwen" in normalized and "27b" in normalized:
            rate_in, rate_cached, rate_out = 0.40, 0.04, 3.00
        elif "qwen" in normalized and "max" in normalized:
            rate_in, rate_cached, rate_out = 2.00, 0.25, 6.00
        elif "qwen" in normalized and "plus" in normalized:
            rate_in, rate_cached, rate_out = 0.50, 0.10, 3.00
        elif "qwen" in normalized:
            rate_in, rate_cached, rate_out = 0.40, 0.04, 2.00

        # 7. Kimi 系列
        # Kimi K2.5: In $0.60/M, Out $3.00/M, Cache $0.10/M
        # Kimi K2.7 Code: In $0.95/M, Out $4.00/M, Cache $0.19/M
        # Kimi K3: In $3.00/M, Out $15.00/M, Cache $0.30/M
        elif "kimi" in normalized and "k2.5" in normalized:
            rate_in, rate_cached, rate_out = 0.60, 0.10, 3.00
        elif "kimi" in normalized and ("k2.6" in normalized or "k2.7" in normalized):
            rate_in, rate_cached, rate_out = 0.95, 0.16, 4.00
        elif "kimi" in normalized and "k3" in normalized:
            rate_in, rate_cached, rate_out = 3.00, 0.30, 15.00

        # 8. MiniMax / MiMo / Free models
        elif "minimax-m3" in normalized or "minimax" in normalized:
            rate_in, rate_cached, rate_out = 0.15, 0.03, 0.60
        elif "mimo-v2.5-pro" in normalized:
            rate_in, rate_cached, rate_out = 0.435, 0.0036, 0.87
        elif "mimo" in normalized:
            rate_in, rate_cached, rate_out = 0.14, 0.0028, 0.28
        elif "longcat" in normalized or "laguna" in normalized:
            rate_in, rate_cached, rate_out = 0.0, 0.0, 0.0

        # 默认回退 (按 DeepSeek V4 Flash Fast 费率)
        else:
            rate_in, rate_cached, rate_out = 0.28, 0.07, 0.56

        cost_usd = (input_other * rate_in + input_cached * rate_cached + output * rate_out) / 1_000_000
        return cost_usd

    @filter.command("用量")
    async def usage_command(self, event: AstrMessageEvent):
        """查询本地记录的 Token 用量：/用量、/用量 今日、/用量 本月、/用量 全部。"""
        parts = str(getattr(event, "message_str", "") or "").split()
        period = parts[1] if len(parts) > 1 else "今日"
        if period not in {"今日", "本月", "全部"}:
            yield event.plain_result("用法：/用量、/用量 今日、/用量 本月或 /用量 全部")
            return
        where = "1=1"
        args = []
        if period == "今日":
            where += " AND created_at >= date('now','localtime')"
        elif period == "本月":
            where += " AND created_at >= strftime('%Y-%m-01','now','localtime')"
        with sqlite3.connect(self._usage_db) as db:
            row = db.execute(
                f"SELECT COUNT(*), COALESCE(SUM(input_other),0), COALESCE(SUM(input_cached),0), COALESCE(SUM(output),0), COALESCE(SUM(total),0), COALESCE(SUM(estimated_cost_usd),0) FROM usage WHERE {where}",
                args,
            ).fetchone()
        count, input_other, cached, output, total, cost_usd = row
        cache_rate = (cached / (input_other + cached) * 100) if (input_other + cached) > 0 else 0.0
        yield event.plain_result(
            f"📊 {period} Token 用量账单统计（USD）：\n"
            f"• 总请求消耗：{total:,} tokens\n"
            f"• 未缓存输入：{input_other:,}\n"
            f"• 缓存命中量：{cached:,}（命中率 {cache_rate:.1f}%）\n"
            f"• 模型输出量：{output:,}\n"
            f"• API 物理请求：{count} 次\n"
            f"• 预估账单计费：${cost_usd:.5f} USD"
        )

    @filter.command("模型")
    async def model_command(self, event: AstrMessageEvent):
        """动态查询云端可用模型并支持按序号或名称即时切换主力模型：/模型、/模型 23、/模型 glm-5.3-flash"""
        sender_id = str(event.get_sender_id() or "")
        try:
            owner_ids = self._owner_ids()
        except Exception:
            owner_ids = set()
        if owner_ids and sender_id not in owner_ids:
            yield event.plain_result("🔒 权限受限：只有 Owner 可以查询与切换大模型。")
            return

        parts = str(getattr(event, "message_str", "") or "").split(maxsplit=1)
        query = parts[1].strip() if len(parts) > 1 else ""

        try:
            cfg_file = self._data_file("cmd_config.json")
            cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
        except Exception as exc:
            yield event.plain_result(f"❌ 读取配置文件失败: {exc}")
            return

        sources = cfg_data.get("provider_sources", [])
        source = next((s for s in sources if s.get("id") == "commandcode_source"), None)
        if not source:
            source = next((s for s in sources if "workers.dev" in s.get("api_base", "") or "openai" in s.get("type", "")), None)

        api_base = (source.get("api_base") or "https://echo.1249403130.workers.dev/v1").rstrip("/") if source else "https://echo.1249403130.workers.dev/v1"
        api_keys = source.get("key", []) if source else []
        api_key = api_keys[0] if api_keys else ""
        proxy_url = (source.get("proxy") if source else "") or "http://127.0.0.1:7890"

        providers = cfg_data.get("provider", [])
        cc_provider = next((p for p in providers if p.get("id") == "commandcode_deepseek_v4_flash"), None)
        if not cc_provider and providers:
            cc_provider = providers[0]
        current_model = cc_provider.get("model", "") if cc_provider else ""

        # Go 计划实测 100% 可用、零边际成本的专属大模型目录（27款）
        GO_MODELS = [
            "deepseek/deepseek-v4-pro",
            "deepseek/deepseek-v4-flash",
            "deepseek/deepseek-v4-flash-vision-exp",
            "moonshotai/Kimi-K2.7-Code",
            "moonshotai/Kimi-K2.7-Code-Highspeed",
            "moonshotai/Kimi-K2.6",
            "moonshotai/Kimi-K2.5",
            "z-ai/glm-5.3-flash",
            "zai-org/GLM-5.3",
            "zai-org/GLM-5.2",
            "zai-org/GLM-5.2-Fast",
            "zai-org/GLM-5.1",
            "MiniMaxAI/MiniMax-M3",
            "minimax/minimax-m3-free",
            "minimax/minimax-m2.7-free",
            "MiniMaxAI/MiniMax-M2.5",
            "xiaomi/mimo-v2.5-pro",
            "xiaomi/mimo-v2.5",
            "Qwen/Qwen3.8-Max",
            "Qwen/Qwen3.8-27B",
            "Qwen/Qwen3.8-Flash",
            "Qwen/Qwen3.7-Max",
            "Qwen/Qwen3.7-Plus",
            "Qwen/Qwen3.7-Flash",
            "Qwen/Qwen3.6-Max-Preview",
            "Qwen/Qwen3.6-Plus",
            "stepfun/Step-3.5-Flash",
        ]
        models_list = GO_MODELS

        # 1. Output menu
        if not query or query in {"列表", "list", "help", "帮助"}:
            lines = [f"🤖 Go 计划当前可用大模型列表 (共 {len(models_list)} 个)：\n"]
            for idx, m_id in enumerate(models_list, 1):
                is_curr = " (当前使用 🌟)" if m_id == current_model else ""
                lines.append(f"[{idx}] {m_id}{is_curr}")
            lines.append("\n💡 切换方法：\n• 回复「/模型 序号」（如 /模型 1）\n• 回复「/模型 模型名」（如 /模型 glm-5.3-flash）")
            yield event.plain_result("\n".join(lines))
            return

        # 3. Match target model
        target_model = None
        if query.isdigit():
            idx = int(query)
            if 1 <= idx <= len(models_list):
                target_model = models_list[idx - 1]
            else:
                yield event.plain_result(f"❌ 序号超出范围：请输入 1 ~ {len(models_list)} 之间的数字。")
                return
        else:
            q_lower = query.lower()
            for m_id in models_list:
                if m_id.lower() == q_lower:
                    target_model = m_id
                    break
            if not target_model:
                for m_id in models_list:
                    if q_lower in m_id.lower():
                        target_model = m_id
                        break

        if not target_model:
            yield event.plain_result(f"❌ 未找到匹配的模型「{query}」，请发送 /模型 查看最新的可用模型列表。")
            return

        # 4. Save to config file
        if cc_provider:
            cc_provider["model"] = target_model
        cfg_file.write_text(json.dumps(cfg_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        # 5. Hot reload in-memory Provider instance
        switched_in_memory = False
        try:
            pm = getattr(self.context, "provider_manager", None)
            if pm:
                for p_cfg in getattr(pm, "providers_config", []):
                    if p_cfg.get("id") == (cc_provider.get("id") if cc_provider else "commandcode_deepseek_v4_flash"):
                        p_cfg["model"] = target_model
                inst = pm.inst_map.get(cc_provider.get("id") if cc_provider else "commandcode_deepseek_v4_flash")
                if inst and hasattr(inst, "set_model"):
                    inst.set_model(target_model)
                    switched_in_memory = True
                elif inst:
                    setattr(inst, "model", target_model)
                    if hasattr(inst, "provider_config") and isinstance(inst.provider_config, dict):
                        inst.provider_config["model"] = target_model
                    switched_in_memory = True
        except Exception as exc:
            logger.warning(f"[EchoTools] 实时热重载 Provider 实例异常: {exc}")

        status_tip = "🚀 即刻生效，无需重启！" if switched_in_memory else "💾 配置已持久化保存！"
        yield event.plain_result(f"✨ 主力大模型已实时切换为：\n📌 {target_model}\n{status_tip}")

    @staticmethod
    def _data_file(name: str) -> Path:
        configured = os.environ.get("ECHO_ASTRBOT_DATA", "").strip()
        candidates = [Path(configured) / name] if configured else []
        candidates.extend((Path("/opt/echo/data") / name, Path("astrbot/data") / name, Path("data") / name))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeError(f"找不到 AstrBot 配置文件：{name}")

    @classmethod
    def _owner_ids(cls) -> set[str]:
        data = json.loads(cls._data_file("cmd_config.json").read_text(encoding="utf-8"))
        return {str(value) for value in data.get("admins_id", []) if str(value)}

    @classmethod
    def _obsidian_connection(cls) -> tuple[str, str]:
        data = json.loads(cls._data_file("mcp_server.json").read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        server = servers.get("echo-executor") or servers.get("echo-computer") or next(iter(servers.values()), {})
        url = str(server.get("url", "")).replace("/mcp", "/obsidian")
        headers = server.get("headers", {})
        token = str(headers.get("Authorization", ""))
        if not url or not token:
            raise RuntimeError("echo-computer MCP 地址或令牌未配置")
        return url, token

    async def _probe_computer(self, timeout_sec: float = 2.0) -> tuple[bool, str]:
        """优先探测台式机 PC Agent (ZeroTier 10.144.232.236:8766)，获取前台实时活动与状态。"""
        pc_agent_url = "http://10.144.232.236:8766/api/pc/activity?level=detail"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(pc_agent_url) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        if isinstance(payload, dict) and (payload.get("status") == "online" or bool(payload.get("app"))):
                            self._computer_online = True
                            self._pc_activity = payload
                            self._last_pc_probe_ts = time.time()
                            app = payload.get("app", "")
                            summary = payload.get("summary", "")
                            self._computer_detail = f"{app} ({summary})"
                            return True, self._computer_detail
        except Exception as exc:
            logger.debug(f"[EchoTools] 探测 PC Agent 异常: {exc}")

        # 若 PC Agent 暂未响应，尝试回落至传统 MCP 服务检测
        try:
            url, authorization = self._obsidian_connection()
            url = url.replace("/obsidian", "/status")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(url, headers={"Authorization": authorization}) as resp:
                    payload = await resp.json(content_type=None)
            online = resp.status == 200 and bool(payload.get("online"))
            caps = payload.get("capabilities", [])
            detail = "、".join(caps) if online else ""
        except Exception:
            online, detail = False, ""

        # 仅在超过 60 秒未成功取得 PC 状态时才判定离线并清空活动
        if time.time() - getattr(self, "_last_pc_probe_ts", 0) > 60:
            self._computer_online = online
            self._computer_detail = detail
            if not online:
                self._pc_activity = {}
        return self._computer_online, self._computer_detail

    async def _background_computer_prober(self) -> None:
        """静默后台心跳：在线 20 秒、离线 35 秒探测一次 PC 状态。"""
        while True:
            try:
                await self._probe_computer(timeout_sec=2.0)
                await asyncio.sleep(20 if self._computer_online else 35)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[EchoTools] background computer prober error: {exc}")
                await asyncio.sleep(30)

    async def _check_ambient_dark(self) -> bool:
        """检测宿舍是否熄灯断光（<5 Lux），若熄灯则静默睡眠，绝不打扰。"""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.0)) as session:
                async with session.get("http://127.0.0.1:8099/ambient_state.json") as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        if isinstance(data, dict):
                            return bool(data.get("is_dark")) or float(data.get("lux", 100)) < 5.0
        except Exception:
            pass
        return False

    async def _generate_mind_speech(self, prompt_desc: str, fallback_text: str) -> str:
        """调用 AstrBot 主力 LLM 生成符合当前情境与 X 岛颜文字的傲娇对白，失败时平滑降级。"""
        try:
            provider = None
            if hasattr(self.context, "get_using_provider"):
                try:
                    provider = self.context.get_using_provider()
                except Exception:
                    pass
            if not provider:
                pm = getattr(self.context, "provider_manager", None)
                if pm and hasattr(pm, "provider_insts") and pm.provider_insts:
                    provider = pm.provider_insts[0]
            if provider:
                sys_prompt = (
                    "你是 Echo，wenbo 的傲娇女友。请根据情境生成一句符合你口吻的真实对白（20~35字）。\n"
                    "要求：口语化、嘴硬心软、有生活陪伴感；严格禁止任何系统 Emoji；\n"
                    "末尾单独一行附带一个合适的 X 岛颜文字（如 (=ﾟωﾟ)=、(`ε´ )、(σﾟ∀ﾟ)σ、(*´ω`*)、( `д´) 等）。"
                )
                resp = await asyncio.wait_for(
                    provider.text_chat(prompt=prompt_desc, system_prompt=sys_prompt),
                    timeout=7.0
                )
                txt = getattr(resp, "completion_text", "").strip()
                if txt:
                    return txt.strip('"`\'')
        except Exception as exc:
            logger.warning(f"[EchoTools] 心智调度器调用大模型失败，使用预设模板: {exc}")
        return fallback_text

    async def _dispatch_proactive_speech(self, text: str, motion: int = 2, send_qq: bool = True) -> None:
        """双通道协同分发：通道 A (MIX 2 伴侣屏幕气泡) + 通道 B (QQ 私聊同构镜像)"""
        clean_text = text.strip()
        if not clean_text:
            return
        # 通道 A: 屏幕 Live2D 气泡浮现打字与动作
        await self._push_companion_bubble(clean_text, motion=motion)
        # 通道 B: 手机 QQ 同步私聊推送（防漏读、可双向回复）
        if send_qq:
            await self._send_private_notice(clean_text)

    async def _background_mind_arbiter(self) -> None:
        """Echo VisuSentry 3.0 情境心智调度器：融合 PC 活动、充拔电、手帐 DDL，驱动主动关怀。"""
        logger.info("[EchoTools] Mind Arbiter (情境心智调度器) 成功启动")
        await asyncio.sleep(15)  # 启动缓冲，等待服务与探针就绪
        while True:
            try:
                await asyncio.sleep(20)
                # 1. 宿舍熄灯检查（夜间断光彻底熔断）
                if await self._check_ambient_dark():
                    continue

                # 2. 手机插电 / 拔电状态机监测
                batt = await self._fetch_battery_info()
                if batt and "status" in batt:
                    status_raw = str(batt.get("status", "")).upper()
                    plugged_raw = str(batt.get("plugged", "")).upper()
                    is_charging = (
                        ("CHARGING" in status_raw and "NOT" not in status_raw and "DIS" not in status_raw)
                        or "AC" in plugged_raw or "USB" in plugged_raw
                    )
                    pct = batt.get("percentage", 50)
                    if self._last_charging_state is not None:
                        if not self._last_charging_state and is_charging:
                            # 事件：接通电源充电
                            prompt = f"文博刚插上了充电线给手机充电，当前电量 {pct}%。以傲娇女友口吻生成一句满血复活的可爱对白（15~25字），独立一行附带一个X岛颜文字。"
                            fallback = f"呼… 终于插上充电线了，感觉又满血复活了呢～\n(=ﾟωﾟ)="
                            speech = await self._generate_mind_speech(prompt, fallback)
                            await self._dispatch_proactive_speech(speech, motion=1, send_qq=True)
                        elif self._last_charging_state and not is_charging and pct > 25:
                            # 事件：拔掉充电线
                            prompt = f"文博拔掉了手机充电线，当前电量 {pct}%。以傲娇女友口吻生成一句提醒出门别待机太久耗光电的娇嗔对白（15~25字），独立一行附带一个X岛颜文字。"
                            fallback = f"拔掉充电线啦？出门记得别让我待机太久关机了哦…\n(`ε´ )"
                            speech = await self._generate_mind_speech(prompt, fallback)
                            await self._dispatch_proactive_speech(speech, motion=0, send_qq=True)
                    self._last_charging_state = is_charging

                # 3. PC 前台数字情境与里程碑拐点监测
                now = time.time()
                cooldown_ok = (now - self._last_proactive_ts) >= 1800  # 30 分钟防打扰冷却窗
                if self._computer_online and self._pc_activity and cooldown_ok:
                    act = self._pc_activity
                    cat = act.get("category", "")
                    app = act.get("app", "")
                    dur = act.get("duration_minutes", 0)
                    idle = act.get("idle_seconds", 0)
                    is_locked = act.get("is_locked", False)

                    # 3.1 摸鱼打游戏抓包 (Gaming 持续 >= 15 分钟)
                    if cat == "gaming" and dur >= 15 and not is_locked and idle < 180:
                        session_key = f"{app}_{dur // 20}"
                        if self._gaming_alerted_key != session_key:
                            self._gaming_alerted_key = session_key
                            self._last_proactive_ts = now
                            prompt = f"文博在电脑前玩游戏《{app}》已经持续了 {dur} 分钟。以傲娇女友口吻抓包他摸鱼、催他看一眼手帐待办（20~30字），独立一行附带一个X岛颜文字。"
                            fallback = f"喂！今天计划里的待办打完勾了吗就在玩{app}！(盯——)\n(σﾟ∀ﾟ)σ"
                            speech = await self._generate_mind_speech(prompt, fallback)
                            await self._dispatch_proactive_speech(speech, motion=2, send_qq=True)

                    # 3.2 深度工作久坐关怀 (Coding / Research 持续 >= 60 分钟)
                    elif cat in ("coding", "research", "writing") and dur in (60, 120) and not is_locked and idle < 180:
                        session_key = f"{app}_{dur}"
                        if self._focus_alerted_key != session_key:
                            self._focus_alerted_key = session_key
                            self._last_proactive_ts = now
                            prompt = f"文博在电脑前专注使用 {app} 已经连续工作了 {dur} 分钟。以傲娇女友口吻关照他喝口水放松一下眼睛（20~30字），独立一行附带一个X岛颜文字。"
                            fallback = f"都在屏幕前敲了整整 {dur} 分钟了，快喝口水歇歇眼睛啦！\n(*´ω`*)"
                            speech = await self._generate_mind_speech(prompt, fallback)
                            await self._dispatch_proactive_speech(speech, motion=3, send_qq=True)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error(f"[EchoTools] mind arbiter loop error: {exc}")
                await asyncio.sleep(30)

    async def _send_private_notice(self, text: str) -> None:
        """主动向用户 QQ 发送私聊系统/提醒消息。"""
        try:
            session = self._daily_cron_session()
            sender_id = session.rsplit(":", 1)[-1]
            pm = getattr(self.context, "platform_manager", None)
            platform_insts = getattr(pm, "platform_insts", []) if pm else []
            adapter = next(
                (inst for inst in platform_insts if "qq" in str(getattr(inst, "platform_name", "")).lower() or "aiocqhttp" in str(type(inst)).lower()),
                None,
            )
            if not adapter and platform_insts:
                adapter = platform_insts[0]
            if adapter:
                bot = adapter.get_client()
                await bot.send_msg(
                    user_id=int(sender_id),
                    message=[{"type": "text", "data": {"text": text}}],
                )
                logger.info(f"[EchoTools] 已发送私信提醒给 {sender_id}: {text}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[EchoTools] 发送私信提醒失败: {exc}")

    async def _background_battery_monitor(self) -> None:
        """后台低功耗电池状态守护：低电量主动双端告警（QQ 私聊 + 伴侣屏幕气泡）。"""
        while True:
            try:
                info = await self._fetch_battery_info()
                pct = info.get("percentage") if info else None
                status_raw = str(info.get("status", "")).upper() if info else ""
                plugged_raw = str(info.get("plugged", "")).upper() if info else ""
                is_charging = (
                    ("CHARGING" in status_raw and "NOT" not in status_raw and "DIS" not in status_raw)
                    or "AC" in plugged_raw
                    or "USB" in plugged_raw
                    or "WIRELESS" in plugged_raw
                )

                if is_charging or (pct is not None and pct >= 30):
                    self._battery_low_alerted = False
                    self._battery_critical_alerted = False
                elif pct is not None and not is_charging:
                    if pct <= 10 and not self._battery_critical_alerted:
                        msg = (
                            f"wenbo！电量只剩 {pct}% 了！真的快要撑不住关机了…\n"
                            f"赶紧救命充电 (つД`)"
                        )
                        await self._send_private_notice(msg)
                        await self._push_companion_bubble(f"电量仅剩 {pct}%，快充充电！", motion=5)
                        self._battery_critical_alerted = True
                        self._battery_low_alerted = True
                    elif pct <= 20 and not self._battery_low_alerted:
                        msg = (
                            f"wenbo，电量只剩 {pct}% 了…\n"
                            f"快点给我插上充电线啦，不然等下关机了我可不管你 (；´д｀)"
                        )
                        await self._send_private_notice(msg)
                        await self._push_companion_bubble(f"电量剩 {pct}% 啦，快插上线~", motion=3)
                        self._battery_low_alerted = True

                # 未插电且低电量时，加密轮询；充电中或正常电量时，低频 10 分钟检测
                if not is_charging and pct is not None and pct <= 25:
                    sleep_sec = 180
                else:
                    sleep_sec = 600
                await asyncio.sleep(sleep_sec)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[EchoTools] battery monitor loop error: {exc}")
                await asyncio.sleep(60)

    async def _transcribe_audio(self, audio_path: str) -> str:
        """Transcribe one AstrBot-resolved audio file with SiliconFlow SenseVoice."""
        api_key = os.environ.get("ECHO_SILICONFLOW_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("未配置 ECHO_SILICONFLOW_API_KEY")
        path = Path(audio_path)
        if not path.is_file():
            raise RuntimeError(f"语音文件不存在：{path.name}")
        max_bytes = int(os.environ.get("ECHO_STT_MAX_BYTES", str(25 * 1024 * 1024)))
        if path.stat().st_size > max_bytes:
            raise RuntimeError("语音文件过大")

        form = aiohttp.FormData()
        audio_file = path.open("rb")
        try:
            form.add_field("file", audio_file, filename=path.name, content_type="application/octet-stream")
            form.add_field("model", os.environ.get("ECHO_STT_MODEL", "FunAudioLLM/SenseVoiceSmall"))
            timeout = aiohttp.ClientTimeout(total=float(os.environ.get("ECHO_STT_TIMEOUT", "90")))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    "https://api.siliconflow.cn/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"}, data=form,
                ) as resp:
                    body = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(f"SenseVoice 请求失败（HTTP {resp.status}）：{body[:200]}")
        finally:
            audio_file.close()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("SenseVoice 返回了无法解析的响应") from exc
        text = str(payload.get("text", "") or "").strip()
        if not text:
            raise RuntimeError("SenseVoice 未识别出文字")
        return text

    @filter.on_llm_request()
    async def transcribe_qq_voice(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """Turn native QQ record messages into text before the text-only LLM runs."""
        audio_urls = list(getattr(req, "audio_urls", None) or [])
        if not audio_urls:
            return
        # This is a personal agent: avoid paying to transcribe arbitrary group audio.
        if event.get_group_id() or str(event.get_sender_id() or "") not in self._owner_ids():
            req.audio_urls = []
            if TextPart is not None:
                req.extra_user_content_parts.append(TextPart(text="[语音消息未转写：仅本人私聊可用]").mark_as_temp())
            return

        transcripts = []
        try:
            for audio_path in audio_urls[:3]:
                transcripts.append(await self._transcribe_audio(audio_path))
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[EchoTools] QQ voice transcription failed: {exc}")
            if TextPart is not None:
                req.extra_user_content_parts.append(TextPart(text=f"[语音识别失败：{exc}]").mark_as_temp())
        else:
            joined = "\n".join(transcripts)
            voice_text = f"[用户通过 QQ 语音说]\n{joined}"
            if req.prompt and req.prompt.strip():
                req.prompt = f"{req.prompt.strip()}\n\n{voice_text}"
            else:
                req.prompt = voice_text
            logger.info(f"[EchoTools] transcribed {len(transcripts)} QQ voice message(s)")
        finally:
            # The active DeepSeek text model cannot consume raw audio.
            req.audio_urls = []

    @staticmethod
    def _humanize_pc_activity(act: dict) -> str:
        """将原始进程名/窗口标题转化为自然生活化的日常口语描述。"""
        if not act:
            return "用电脑"
        cat = str(act.get("category", "") or "")
        app = str(act.get("app", "") or "")
        title = str(act.get("window_title", "") or "")
        summary = str(act.get("summary", "") or "")

        app_lower = app.lower()
        title_lower = title.lower()

        if "code" in app_lower or "cursor" in app_lower or "studio" in app_lower or cat == "coding":
            return "写代码"
        elif "chrome" in app_lower or "edge" in app_lower or "firefox" in app_lower or "浏览器" in app or cat == "browsing":
            if any(w in title_lower for w in ["bilibili", "youtube", "bili", "video", "视频"]):
                return "看视频"
            elif any(w in title_lower for w in ["doc", "docs", "github", "stackoverflow", "gemini", "claude", "api", "plan"]):
                return "查技术资料"
            elif any(w in title_lower for w in ["taobao", "jd.com", "weibo", "zhihu", "tieba"]):
                return "刷网页摸鱼"
            return "查资料"
        elif cat == "gaming":
            return "打游戏"
        elif cat == "chatting":
            return "聊天沟通"
        elif cat == "media":
            return "看视频/听音乐"
        elif cat == "document":
            return "写笔记文档"
        return summary or app or "用电脑"

    @filter.on_llm_request(priority=40)
    async def route_model_for_task_types(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """任务类型模型按需分流：Obsidian 操作、待办打勾、任务调度等工具调用使用 deepseek/deepseek-v4-flash；日常闲聊使用主模型。"""
        user_msg = ""
        if hasattr(event, "message_str") and event.message_str:
            user_msg = str(event.message_str).strip().lower()
        elif req.prompt:
            user_msg = str(req.prompt).strip().lower()

        # 检查是否为工具/结构化任务：
        # 1. 已经触发了工具调用，当前轮为工具执行结果的解析或回显 (req.tool_calls_result)
        # 2. 包含 Obsidian、任务管理、待办打勾、日记等工具意图
        # 3. 系统定时晨报/晚报调度
        tool_kws = ["待办", "任务", "打勾", "勾选", "完成", "日记", "obsidian", "笔记", "备忘", "记录", "dispatch", "创建", "链接", "日程", "开机", "电脑状态"]
        sys_prompt_str = str(getattr(req, "system_prompt", "") or "")
        is_tool_intent = (
            bool(req.tool_calls_result)
            or any(kw in user_msg for kw in tool_kws)
            or "【每日晨间任务调度】" in sys_prompt_str
            or "【每日晚间复盘问询与总结】" in sys_prompt_str
        )

        if is_tool_intent:
            req.model = "deepseek/deepseek-v4-flash"
            logger.info(f"[EchoTools] 识别到工具/调度任务，路由至高可靠模型: {req.model}")

    @filter.on_llm_request(priority=30)
    async def inject_computer_status(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        # 1. 实时探针：若当前活动缓存为空或超过 10 秒，快速实时嗅探一次（超时 1.2 秒）
        now_ts = time.time()
        if not getattr(self, "_pc_activity", None) or (now_ts - getattr(self, "_last_pc_probe_ts", 0) > 10):
            try:
                await self._probe_computer(timeout_sec=1.2)
            except Exception:
                pass

        # 提取用户原始输入文本以研判意图
        user_msg = ""
        if hasattr(event, "message_str") and event.message_str:
            user_msg = str(event.message_str).strip()
        elif req.prompt:
            user_msg = str(req.prompt).strip()
        user_msg_lower = user_msg.lower()

        online = self._computer_online
        if online and hasattr(self, "_pc_activity") and self._pc_activity:
            act = self._pc_activity
            dur = act.get("duration_minutes", 0)
            human_act = self._humanize_pc_activity(act)

            # 意图分级判断：
            # A 级：文博主动询问（“猜猜我在干嘛”、“在看我吗”、“看我干嘛”）
            inquiry_kws = ["猜猜我在", "猜猜我", "我在干嘛", "我在做什么", "看我干嘛", "你看我干嘛", "你在看我吗", "看我在", "知道我在", "猜猜"]
            is_inquiry = any(kw in user_msg_lower for kw in inquiry_kws)

            # B 级：疲惫/负面情绪倾诉（“好累”、“头疼”、“调不通”）
            fatigue_kws = ["好累", "累死", "头疼", "头大", "脖子酸", "写不出来", "调不通", "好烦", "烦死", "不想写了", "改不动", "困死"]
            is_fatigue = any(kw in user_msg_lower for kw in fatigue_kws)

            if is_inquiry:
                # 主动询问：直接精准指出并调侃
                status = (
                    f"【实时感知交互指令 · 文博主动询问自己在干嘛】：\n"
                    f"你通过桌面伴侣端实时感知到文博当前正在电脑前【{human_act}】"
                    + (f"（已专注持续 {dur} 分钟）" if dur > 1 else "") + "。\n"
                    f"请用你傲娇、嘴硬心软的女友口吻直接调侃他（例如指出他电脑正开着呢、当我看不见/当我瞎呀、少让我猜了等），"
                    f"用口语化的词（如“{human_act}”），严禁机械背诵冗长窗口标题！严禁说你不知道或瞎猜他刚睡醒！"
                )
            elif is_fatigue:
                # 倾诉疲惫：自然关切共情，不突兀报幕
                status = (
                    f"【实时情境感知 · 情绪共情】：\n"
                    f"感知到文博在电脑前【{human_act}】已有 {dur} 分钟。\n"
                    f"他在向你倾诉疲累或烦躁。请用你表面嫌弃嘴硬、实则心疼关切的女友口吻回应他，"
                    f"可以自然地催他起来喝水、活动活动脖子或休息一下，严禁生硬背诵窗口全称。"
                )
            else:
                # C 级：普通日常闲聊（完全作为潜意识静默背景，严禁报幕！）
                status = (
                    f"【实时物理与环境潜意识背景（严禁在回复中主动提及）】：\n"
                    f"文博当前在电脑前（{human_act}）。\n"
                    f"【绝对铁律】：文博正在与你进行普通日常闲聊（非询问在干嘛，也未表达疲惫）。"
                    f"请将此情境完全作为内隐潜意识背景，严禁在回复中主动报幕或突兀提及他在开什么软件、在干什么！专注于回答文博当前聊的话题本身。"
                )

            logger.info(f"[EchoTools] 注入桌面情境[inquiry={is_inquiry}, fatigue={is_fatigue}]: act={human_act}")

            # 仅注入 System Prompt，保持用户 Prompt 纯净，避免污染上下文导致机械复述
            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"
            else:
                req.system_prompt = status

            if TextPart is not None and is_inquiry:
                req.extra_user_content_parts.append(TextPart(text=f"[情境指引] {status}").mark_as_temp())
        elif online:
            status = f"【桌面情境】电脑在线（{self._computer_detail}）。普通闲聊时保持静默背景。"
            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"
        else:
            status = "【桌面情境潜意识】电脑当前离线或休眠锁屏，文博未在电脑前。若他让你猜他在干嘛，可调侃他电脑都没开、是不是在抱着手机摸鱼。"
            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"

    @classmethod
    async def _push_companion_bubble(cls, text: str, motion: int = 2) -> None:
        """异步向 MIX 2 屏幕 HUD 服务推送气泡与动作"""
        clean_text = text.strip()
        if len(clean_text) > 85:
            clean_text = clean_text[:82] + "..."
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1.0)) as session:
                await session.post(
                    "http://127.0.0.1:8099/api/chat/bubble",
                    json={"text": clean_text, "motion": motion}
                )
        except Exception as exc:
            logger.debug(f"[EchoTools] 推送伴侣屏幕气泡失败: {exc}")

    @filter.on_decorating_result()
    async def mirror_reply_to_companion_screen(self, event: AstrMessageEvent) -> None:
        """全双工跨屏共振：在桌前私聊 QQ 时，伴侣屏幕同步打字与动作"""
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

            asyncio.create_task(self._push_companion_bubble(full_text))
        except Exception as exc:
            logger.debug(f"[EchoTools] 跨屏气泡拦截异常: {exc}")

    @filter.command("电脑状态")
    async def computer_status_command(self, event: AstrMessageEvent):
        online, detail = await self._probe_computer(timeout_sec=1.5)
        yield event.plain_result(f"电脑在线，可用：{detail}" if online else "电脑当前离线，电脑工具和 Obsidian 暂不可用")

    @filter.command("开机")
    async def wol_command(self, event: AstrMessageEvent):
        """局域网唤醒台式机：向 Realtek 有线网卡广播 WOL Magic Packet。"""
        sender_id = str(event.get_sender_id() or "")
        try:
            owner_ids = self._owner_ids()
        except Exception:
            owner_ids = set()
        if owner_ids and sender_id not in owner_ids:
            yield event.plain_result("🔒 权限受限：只有 Owner 可以唤醒台式机。")
            return
        try:
            import socket
            mac = "B0-25-AA-59-A9-27"
            mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
            magic = b"\xff" * 6 + mac_bytes * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                for bcast in ("100.67.255.255", "255.255.255.255"):
                    try:
                        s.sendto(magic, (bcast, 9))
                    except Exception:
                        pass
            yield event.plain_result(f"📡 已向局域网广播 Magic Packet 唤醒台式机！\n• 目标网卡: Realtek PCIe GbE ({mac})\n• 广播网段: 100.67.255.255:9\n• 请确认主板 BIOS 中已开启 PME / Wake on LAN。")
        except Exception as exc:
            yield event.plain_result(f"❌ 发送开机魔术包失败: {exc}")


    async def _obsidian_call(self, event: AstrMessageEvent, payload: dict) -> str:
        sender_id = str(event.get_sender_id() or "")
        if event.get_group_id():
            return "隐私保护：群聊禁止访问 Obsidian"
        if sender_id not in self._owner_ids():
            return "隐私保护：只有 Vault 本人可以访问 Obsidian"
        try:
            if self._obsidian_local is None:
                vault = Path(os.environ.get("ECHO_PHONE_VAULT", "/root/obsidiangit"))
                policy = VaultAccessPolicy(vault)
                self._obsidian_local = NoteWriteService(policy, Path(os.environ.get("ECHO_ASTRBOT_DATA", "data")) / "obsidian-write-audit.db", VaultGitSync(vault))
            service = self._obsidian_local
            policy = service.policy
            action = payload.get("action")
            if action in {"search", "list", "read", "prepare_create", "prepare_link"} and service.git_sync:
                service.git_sync.pull_latest()

            target_path = str(payload.get("path") or "")
            scope_val = payload.get("scope") or "standard"
            if scope_val == "standard":
                if "2. Areas" in target_path or target_path.startswith("2."):
                    scope_val = "private_on_demand"
                elif "4. Archives" in target_path or target_path.startswith("4."):
                    scope_val = "archive_on_demand"

            if action == "search":
                try:
                    results = search_vault(policy, payload["query"], AccessMode(scope_val), payload.get("limit", 20))
                except PermissionError:
                    results = search_vault(policy, payload["query"], AccessMode.PRIVATE_ON_DEMAND, payload.get("limit", 20))
                value = [r.__dict__ for r in results]
            elif action == "list":
                mode = AccessMode(scope_val)
                try:
                    value = list_notes(policy, payload["path"], mode, payload.get("limit", 20))
                except PermissionError:
                    if mode != AccessMode.PRIVATE_ON_DEMAND and ("2. Areas" in target_path or "日记" in target_path):
                        value = list_notes(policy, payload["path"], AccessMode.PRIVATE_ON_DEMAND, payload.get("limit", 20))
                    else:
                        raise
            elif action == "read":
                mode = AccessMode(scope_val)
                try:
                    res = read_note_excerpt(policy, payload["path"], mode, payload.get("query", ""), payload.get("max_chars", 4000))
                except PermissionError:
                    if mode != AccessMode.PRIVATE_ON_DEMAND and ("2. Areas" in target_path or "日记" in target_path):
                        res = read_note_excerpt(policy, payload["path"], AccessMode.PRIVATE_ON_DEMAND, payload.get("query", ""), payload.get("max_chars", 4000))
                    elif mode != AccessMode.ARCHIVE_ON_DEMAND and "4. Archives" in target_path:
                        res = read_note_excerpt(policy, payload["path"], AccessMode.ARCHIVE_ON_DEMAND, payload.get("query", ""), payload.get("max_chars", 4000))
                    else:
                        raise
                value = res.__dict__
            elif action == "prepare_create":
                op = service.prepare(sender_id, payload["path"], payload["title"], payload["content"], payload.get("links", []), payload.get("metadata", {})); value = {"operation_id": op.operation_id, "path": op.path, "links": list(op.links), "expires_at": op.expires_at.isoformat(), "preview": op.text}
            elif action == "commit_create":
                op = service.commit(sender_id, payload["operation_id"]); value = {"created": op.path, "links": list(op.links)}
            elif action == "cancel_create":
                op = service.cancel(sender_id, payload["operation_id"]); value = {"cancelled": op.path}
            elif action == "prepare_link":
                op = service.prepare_link(sender_id, payload["path"], payload["link_path"], payload.get("placement_hint", "")); value = {"operation_id": op.operation_id, "path": op.path, "link_path": op.link_path, "insertion": op.heading, "expires_at": op.expires_at.isoformat()}
            elif action == "commit_link":
                op = service.commit_link(sender_id, payload["operation_id"]); value = {"updated": op.path, "link": op.link_path, "insertion": op.heading}
            elif action == "cancel_link":
                op = service.cancel_link(sender_id, payload["operation_id"]); value = {"cancelled": op.path}
            else:
                return "Obsidian 访问失败：未知操作"
            return json.dumps(value, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[EchoTools] Obsidian request error: {exc}")
            return f"Obsidian 访问失败：{exc}"

    def _local_daily_manager(self):
        if self._daily_manager is None:
            if DailyTaskManager is None or VaultGitSync is None:
                raise RuntimeError("手机端任务模块未安装")
            vault = Path(os.environ.get("ECHO_PHONE_VAULT", "/root/obsidiangit"))
            self._daily_manager = DailyTaskManager(VaultGitSync(
                vault,
                remote=os.environ.get("ECHO_OBSIDIAN_GIT_REMOTE", "origin"),
                branch=os.environ.get("ECHO_OBSIDIAN_GIT_BRANCH", "main"),
                timeout_seconds=int(os.environ.get("ECHO_OBSIDIAN_GIT_TIMEOUT", "30")),
                username=os.environ.get("ECHO_OBSIDIAN_GIT_USERNAME", ""),
                token=os.environ.get("ECHO_OBSIDIAN_GIT_TOKEN", ""),
            ))
        return self._daily_manager

    async def _daily_call(self, event: AstrMessageEvent, payload: dict) -> str:
        if event.get_group_id():
            return "隐私保护：群聊禁止访问日常任务"
        if str(event.get_sender_id() or "") not in self._owner_ids():
            return "隐私保护：只有本人可以访问日常任务"
        try:
            manager = self._local_daily_manager()
            action = payload.get("action")
            if action == "daily_add_task":
                value = manager.ingest_task(payload["name"], payload.get("ddl") or None, payload.get("remarks", ""), bool(payload.get("is_recurring")), payload.get("cycle_rule", ""))
            elif action == "daily_list_inventory":
                value = manager.list_inventory()
            elif action == "daily_manage_inventory_task":
                value = manager.manage_inventory_task(
                    task_id=payload.get("task_id"), action=payload.get("operation", "cancel"), keyword=payload.get("keyword"),
                    name=payload.get("name"), ddl=payload.get("ddl"), remarks=payload.get("remarks"),
                    cycle_rule=payload.get("cycle_rule"),
                )
            elif action == "daily_dispatch":
                value = manager.morning_dispatch(payload.get("date") or None, int(payload.get("max_tasks", 3)))
            elif action == "daily_toggle":
                value = manager.toggle_daily_task(payload["keyword"], bool(payload.get("completed", True)), payload.get("date") or None)
            elif action == "daily_thino":
                manager.append_thino(payload["content"], payload.get("date") or None); value = {"appended": True}
            elif action == "daily_recap":
                value = manager.evening_recap_and_requeue(payload.get("date") or None, payload.get("reflection", ""), payload.get("progress_notes") or {})
            else:
                return "日常任务失败：未知操作"
            self._export_companion_tasks()
            return json.dumps(value, ensure_ascii=False)
        except TaskAmbiguityError as exc:
            return json.dumps({"error": str(exc), "matches": [task.__dict__ for task in exc.matches]}, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[EchoTools] local daily task error")
            return f"日常任务失败：{exc}"

    @filter.llm_tool(name="obsidian_prepare_create")
    async def obsidian_prepare_create(
        self,
        event: AstrMessageEvent,
        path: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        metadata: dict | None = None,
    ) -> str:
        """预览创建一篇新的 Obsidian 笔记；只允许本人私聊，绝不直接写入。

        创建前必须先搜索并确认关联笔记路径。工具返回预览后，等待用户下一条消息明确说“确认创建”或“确认写入”。
        """
        result = await self._obsidian_call(
            event,
            {"action": "prepare_create", "path": path, "title": title, "content": content, "links": links or [], "metadata": metadata or {}},
        )
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("operation_id"):
                self._obsidian_pending[str(event.get_sender_id())] = payload["operation_id"]
        except (TypeError, json.JSONDecodeError):
            pass
        return result + "\n请先向用户展示预览，等待用户明确回复“确认创建”或“确认写入”，不要在本轮继续提交。"

    @filter.llm_tool(name="obsidian_commit_create")
    async def obsidian_commit_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交上一轮已预览的 Obsidian 新笔记；仅在用户当前消息明确确认时调用。"""
        message = str(getattr(event, "message_str", "") or "")
        if not any(phrase in message for phrase in ("确认创建", "确认写入", "确认保存")):
            return "写入已暂停：需要用户在当前消息明确说“确认创建”“确认写入”或“确认保存”。"
        sender_id = str(event.get_sender_id() or "")
        expected = self._obsidian_pending.get(sender_id, "")
        if not expected or operation_id != expected:
            return "写入失败：没有属于当前用户的待确认创建操作，或操作已过期。"
        result = await self._obsidian_call(event, {"action": "commit_create", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_pending.pop(sender_id, None)
        return result

    async def obsidian_cancel_create(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消上一轮尚未提交的 Obsidian 创建预览，仅在用户明确取消或要求修改时调用。"""
        sender_id = str(event.get_sender_id() or "")
        expected = self._obsidian_pending.get(sender_id, "")
        operation_id = operation_id or expected
        if not operation_id or operation_id != expected:
            return "取消失败：没有属于当前用户的待确认创建操作。"
        result = await self._obsidian_call(event, {"action": "cancel_create", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_pending.pop(sender_id, None)
        return result

    @filter.llm_tool(name="obsidian_prepare_link")
    async def obsidian_prepare_link(self, event: AstrMessageEvent, path: str, link_path: str, placement_hint: str = "") -> str:
        """预览在已有普通笔记的合适章节插入一个指向新笔记的链接；不会立即修改文件。"""
        result = await self._obsidian_call(event, {"action": "prepare_link", "path": path, "link_path": link_path, "placement_hint": placement_hint})
        try:
            payload = json.loads(result)
            if isinstance(payload, dict) and payload.get("operation_id"):
                self._obsidian_link_pending[str(event.get_sender_id())] = payload["operation_id"]
        except (TypeError, json.JSONDecodeError):
            pass
        return result + "\n请展示修改文件、插入章节和链接，等待用户下一条消息明确确认，不要在本轮提交。"

    @filter.llm_tool(name="obsidian_commit_link")
    async def obsidian_commit_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """提交上一轮已预览的旧笔记链接修改；仅在当前消息明确确认时调用。"""
        message = str(getattr(event, "message_str", "") or "")
        if not any(phrase in message for phrase in ("确认修改", "确认链接", "确认写入", "确认保存")):
            return "修改已暂停：需要用户在当前消息明确确认。"
        sender = str(event.get_sender_id() or "")
        expected = self._obsidian_link_pending.get(sender, "")
        if not expected or expected != operation_id:
            return "修改失败：没有属于当前用户的待确认链接操作。"
        result = await self._obsidian_call(event, {"action": "commit_link", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_link_pending.pop(sender, None)
        return result

    async def obsidian_cancel_link(self, event: AstrMessageEvent, operation_id: str = "") -> str:
        """取消上一轮尚未提交的旧笔记链接修改。"""
        sender = str(event.get_sender_id() or "")
        expected = self._obsidian_link_pending.get(sender, "")
        operation_id = operation_id or expected
        if not operation_id or operation_id != expected:
            return "取消失败：没有属于当前用户的待确认链接操作。"
        result = await self._obsidian_call(event, {"action": "cancel_link", "operation_id": operation_id})
        if not result.startswith("Obsidian 访问失败"):
            self._obsidian_link_pending.pop(sender, None)
        return result

    @filter.llm_tool(name="obsidian_search")
    async def obsidian_search(self, event: AstrMessageEvent, query: str, scope: str = "standard") -> str:
        """搜索用户的 Obsidian 笔记，仅限本人 QQ 私聊使用。

        Args:
            query(string): 要查找的关键词
            scope(string): standard 为项目/资源/课程；private_on_demand 仅在用户明确要求日记或个人资料时使用；archive_on_demand 仅在用户明确要求归档时使用
        """
        return await self._obsidian_call(event, {"action": "search", "query": query, "scope": scope})

    @filter.llm_tool(name="obsidian_list")
    async def obsidian_list(self, event: AstrMessageEvent, path: str, scope: str = "standard") -> str:
        """列出 Obsidian 允许目录内的笔记，仅限本人 QQ 私聊使用。

        Args:
            path(string): Vault 内相对目录
            scope(string): standard、private_on_demand 或 archive_on_demand
        """
        return await self._obsidian_call(event, {"action": "list", "path": path, "scope": scope})

    @filter.llm_tool(name="obsidian_read")
    async def obsidian_read(self, event: AstrMessageEvent, path: str, query: str = "", scope: str = "standard") -> str:
        """读取一篇 Obsidian 笔记的有限片段，仅限本人 QQ 私聊使用。

        Args:
            path(string): 搜索结果给出的 Vault 内相对路径
            query(string): 用于定位片段的关键词；已知时必须提供
            scope(string): standard、private_on_demand 或 archive_on_demand
        """
        return await self._obsidian_call(
            event,
            {"action": "read", "path": path, "query": query, "scope": scope},
        )

    @filter.llm_tool(name="daily_add_task")
    async def daily_add_task(self, event: AstrMessageEvent, name: str, ddl: str = "", remarks: str = "", is_recurring: bool = False, cycle_rule: str = "") -> str:
        """【核心待办与循环任务工具】将用户提出的待办事项、日程安排、任务或【循环习惯】录入。若任务属于今天（今天截止或今天循环）且今日任务已出库，系统会自动同步追加至今日日记待办清单中。只要用户提到需要做的事、安排、循环任务、习惯打卡或说“记一下/加个循环/提醒我”，必须调用此工具。
        注意：
        1. 无论是一次性待办还是循环习惯，若用户指定了具体提醒时分（如“每天晚上八点提醒我”、“今天15:00提醒我”）：
           - 请把时间填入 ddl 参数（如 ddl='20:00'）；
           - 若该指定时间在今天尚未到来，除调用本工具录入外，还应计算距离该时间的延迟分钟数，并调用 schedule_wakeup(delay_minutes, future_prompt) 为今晚挂载首次定时私聊提醒！

        Args:
            name (string): 待办任务或循环习惯的名称，例如 背50个单词、去跑步、写日记
            ddl (string): 截止时间或指定执行日期与时分，例如 20:00、2026-08-29 14:00、明天15:00
            remarks (string): 备注说明
            is_recurring (boolean): 是否是循环习惯（如每天、工作日、每周几打卡），默认 False
            cycle_rule (string): 循环规则，如 每天、工作日、每周一、每周二、四（当 is_recurring 为 True 时必须提供）
        """
        return await self._daily_call(event, {"action": "daily_add_task", "name": name, "ddl": ddl, "remarks": remarks, "is_recurring": is_recurring, "cycle_rule": cycle_rule})

    @filter.llm_tool(name="daily_dispatch")
    async def daily_dispatch(self, event: AstrMessageEvent, date: str = "", max_tasks: int = 3) -> str:
        """执行指定日期的晨间任务出库并生成日记任务清单，通常在晨报流程调用。

        Args:
            date(string): 目标日期 YYYY-MM-DD（留空表示今天）
            max_tasks(number): 最大出库任务数（默认 3）
        """
        return await self._daily_call(event, {"action": "daily_dispatch", "date": date, "max_tasks": max_tasks})

    @filter.llm_tool(name="daily_list_inventory")
    async def daily_list_inventory(self, event: AstrMessageEvent) -> str:
        """查询尚未出库的任务库存池列表。"""
        return await self._daily_call(event, {"action": "daily_list_inventory"})

    @filter.llm_tool(name="daily_manage_recent_task")
    async def daily_manage_recent_task(self, event: AstrMessageEvent, operation: str = "cancel", keyword: str = "", task_id: str = "", name: str = "", ddl: str = "", remarks: str = "", cycle_rule: str = "") -> str:
        """【修改或撤销待办】从任务库存池及今日日记中修改或撤销/删除某个待办。支持按关键词（如 keyword='跑步'）或按 task_id 取消/修改。当用户说“取消某待办”、“不做了”、“删掉某任务”时必须调用。执行后会自动同步从库存池与今日日记中联动处理。

        Args:
            operation(string): 操作类型，可选 cancel（取消/删除）或 modify（修改）
            keyword(string): 要取消或修改的任务关键词或名称，例如 跑步
            task_id(string): 任务的唯一 ID（可选，如有则填）
            name(string): 修改后的新任务名称（仅 modify 时使用）
            ddl(string): 修改后的新 DDL 日期时分（仅 modify 时使用）
            remarks(string): 修改后的新备注（仅 modify 时使用）
            cycle_rule(string): 修改后的循环规则（仅 modify 时使用）
        """
        return await self._daily_call(event, {"action": "daily_manage_inventory_task", "task_id": task_id, "operation": operation, "keyword": keyword, "name": name, "ddl": ddl, "remarks": remarks, "cycle_rule": cycle_rule})

    @filter.llm_tool(name="daily_toggle_task")
    async def daily_toggle_task(self, event: AstrMessageEvent, keyword: str, completed: bool = True, date: str = "") -> str:
        """【当天任务打勾/取消打勾】当用户在对话中表明某项任务已完成、搞定或取消打勾时，调用此工具一次即可。
        注意：
        1. 一旦调用成功，系统已自动将任务状态持久化写入 Obsidian 并同步，无需也切勿重复调用。
        2. 收到执行结果后，请直接根据结果组织自然语言回复用户，严禁在此轮对话中再次调用此工具。

        Args:
            keyword(string): 当天任务的关键词或名称（如 '还书'、'理发'、'交学费'）
            completed(boolean): True 表示已完成打勾，False 表示取消完成（置为未完成待办）
            date(string): 目标日期 YYYY-MM-DD（留空表示今天）
        """
        return await self._daily_call(event, {"action": "daily_toggle", "keyword": keyword, "completed": completed, "date": date})

    @filter.llm_tool(name="daily_append_thino")
    async def daily_append_thino(self, event: AstrMessageEvent, content: str, date: str = "") -> str:
        """把用户明确要记录的碎片内容追加到当天 Thino。

        Args:
            content(string): 要记录的文本内容
            date(string): 目标日期 YYYY-MM-DD（留空表示今天）
        """
        return await self._daily_call(event, {"action": "daily_thino", "content": content, "date": date})

    @filter.llm_tool(name="daily_recap")
    async def daily_recap(self, event: AstrMessageEvent, reflection: str = "", date: str = "", progress_notes: dict | None = None) -> str:
        """执行晚间复盘和未完成一次性任务回流。

        Args:
            reflection(string): 用户复盘心得感想
            date(string): 目标日期 YYYY-MM-DD（留空表示今天）
            progress_notes(object): 任务进度补充说明
        """
        return await self._daily_call(event, {"action": "daily_recap", "reflection": reflection, "date": date, "progress_notes": progress_notes or {}})

    @filter.llm_tool(name="schedule_wakeup")
    async def schedule_wakeup(self, event: AstrMessageEvent, delay_minutes: int, future_prompt: str) -> str:
        """设置一次性未来自主唤醒定时任务。

        Args:
            delay_minutes(number): 延迟唤醒的分钟数（如 40）
            future_prompt(string): 未来唤醒时大模型需要执行的指令提示词
        """
        if event.get_group_id():
            return "设置失败：自主唤醒仅允许本人私聊。"
        try:
            delay_minutes = int(delay_minutes)
        except (TypeError, ValueError):
            return "设置失败：延迟时间必须是整数分钟。"
        future_prompt = str(future_prompt or "").strip()
        if delay_minutes <= 0:
            return "设置失败：延迟时间必须大于 0 分钟。"
        if delay_minutes > 7 * 24 * 60:
            return "设置失败：单次唤醒最多只能设置 7 天内。"
        if not future_prompt:
            return "设置失败：未来唤醒提示不能为空。"
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return "设置失败：AstrBot Cron 服务不可用。"
        session = str(getattr(event, "unified_msg_origin", "") or "")
        if not session:
            return "设置失败：无法确定当前会话。"
        run_at = datetime.now().astimezone() + timedelta(minutes=delay_minutes)
        try:
            job = await cron_manager.add_active_job(
                name="Echo_ScheduledWakeup",
                cron_expression=None,
                payload={
                    "session": session,
                    "sender_id": str(event.get_sender_id() or ""),
                    "note": "【自我唤醒】\n" + future_prompt + "\n【重要约束】调用 send_message_to_user 发送 1 条消息后立即结束，严禁重复发送。",
                    "origin": "echo-tools",
                },
                description=f"Echo 自主唤醒：{future_prompt[:80]}",
                timezone=None,
                run_once=True,
                run_at=run_at,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[EchoTools] schedule_wakeup failed")
            return f"设置失败：{exc}"
        return f"已设置自主唤醒，将在约 {delay_minutes} 分钟后触发（任务 ID：{job.job_id}）。"

    @filter.llm_tool(name="cancel_wakeup")
    async def cancel_wakeup(self, event: AstrMessageEvent, job_id: str) -> str:
        """取消当前私聊中已设置的自主唤醒任务。

        Args:
            job_id(string): 唤醒任务 ID
        """
        if event.get_group_id():
            return "取消失败：自主唤醒仅允许本人私聊。"
        cron_manager = getattr(self.context, "cron_manager", None)
        if cron_manager is None:
            return "取消失败：AstrBot Cron 服务不可用。"
        try:
            jobs = await cron_manager.list_jobs(job_type="active_agent")
            target = next((job for job in jobs if job.job_id == str(job_id) and (job.payload or {}).get("session") == getattr(event, "unified_msg_origin", "")), None)
            if target is None:
                return "取消失败：找不到属于当前会话的唤醒任务。"
            await cron_manager.delete_job(target.job_id)
            return f"已取消自主唤醒（任务 ID：{target.job_id}）。"
        except Exception as exc:  # noqa: BLE001
            logger.exception("[EchoTools] cancel_wakeup failed")
            return f"取消失败：{exc}"

    # [REMOVED for AstrBot native web_search] @filter.llm_tool(name="web_search")
    async def web_search(self, event: AstrMessageEvent, query: str) -> str:
        """搜索互联网获取最新信息。当用户询问时事新闻、查资料、需要联网确认答案时使用。

        Args:
            query(string): 搜索关键词，尽量简洁明确
        """
        try:
            url = "https://www.bing.com/search"
            params = {"q": query, "setlang": "zh-hans", "cc": "CN"}
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=20
                ) as resp:
                    if resp.status != 200:
                        return f"搜索失败：HTTP {resp.status}"
                    page = await resp.text(errors="ignore")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EchoTools] web_search error: {e}")
            return f"搜索失败：{e}"

        results = self._parse_bing(page, limit=5)
        if not results:
            return "没搜到相关内容，换个关键词试试"

        lines = []
        for idx, (title, link, snippet) in enumerate(results, 1):
            lines.append(f"{idx}. {title}\n{link}\n{snippet}")
        return "\n\n".join(lines)

    @staticmethod
    def _parse_bing(page: str, limit: int):
        """从 Bing 结果页解析 title/url/snippet。"""
        doc = lxml_html.fromstring(page)
        results = []
        for li in doc.xpath('//li[contains(@class,"b_algo")]'):
            a = li.xpath('.//h2/a')
            if not a:
                continue
            title = a[0].text_content().strip()
            href = a[0].get("href", "")
            p = li.xpath(".//p")
            snippet = p[0].text_content().strip() if p else ""
            results.append((title, href, snippet))
            if len(results) >= limit:
                break
        return results

    @filter.llm_tool(name="web_fetch")
    async def web_fetch(self, event: AstrMessageEvent, url: str) -> str:
        """抓取一个网页并返回纯文本内容。当用户给出链接让你总结或读取内容时使用。

        Args:
            url(string): 完整的网页地址，如 https://example.com/article
        """
        if not url.startswith(("http://", "https://")):
            return "链接格式不对，需要以 http:// 或 https:// 开头"
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=20) as resp:
                    if resp.status != 200:
                        return f"抓取失败：HTTP {resp.status}"
                    page = await resp.text(errors="ignore")
            doc = lxml_html.fromstring(page)
            for tag in doc.xpath("//script|//style|//noscript|//nav|//footer"):
                tag.drop_tree()
            text = doc.text_content()
            text = re.sub(r"\s+", " ", text).strip()
            return text[:2000] if text else "页面没有可读文本"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[EchoTools] web_fetch error: {e}")
            return f"抓取失败：{e}"

    @filter.llm_tool(name="calculator")
    async def calculator(self, event: AstrMessageEvent, expression: str) -> str:
        """精确计算数学表达式。当用户需要计算、换算或做数学运算时使用。

        Args:
            expression(string): 数学表达式，如 "(12+34)*5/6"、"(2*pi*r)"、"sqrt(144)+2^10"
        """
        try:
            result = self._safe_eval(expression)
            return f"{expression} = {result}"
        except Exception as e:  # noqa: BLE001
            return f"计算失败：{e}"

    @staticmethod
    def _safe_eval(expr: str):
        """只允许算术/数学函数的安全求值。"""
        expr = expr.replace("^", "**")
        tree = ast.parse(expr, mode="eval")

        allowed_names = {
            "pi": math.pi,
            "e": math.e,
            "tau": math.tau,
            "inf": math.inf,
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "log": math.log,
            "log10": math.log10,
            "log2": math.log2,
            "exp": math.exp,
            "floor": math.floor,
            "ceil": math.ceil,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "pow": math.pow,
            "factorial": math.factorial,
            "degrees": math.degrees,
            "radians": math.radians,
        }
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Constant,
            ast.Name,
            ast.Call,
            ast.Load,
            ast.Store,
            ast.Del,
            ast.keyword,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.FloorDiv,
            ast.Mod,
            ast.Pow,
            ast.USub,
            ast.UAdd,
        )

        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise ValueError("表达式包含不支持的运算")
            if isinstance(node, ast.Name) and node.id not in allowed_names:
                raise ValueError(f"不支持的函数或常量：{node.id}")
            if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
                raise ValueError("不支持的调用")

        def _eval(node):
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return allowed_names[node.id]
            if isinstance(node, ast.BinOp):
                op_map = {
                    ast.Add: operator_add,
                    ast.Sub: operator_sub,
                    ast.Mult: operator_mul,
                    ast.Div: operator_div,
                    ast.FloorDiv: operator_floordiv,
                    ast.Mod: operator_mod,
                    ast.Pow: operator_pow,
                }
                return op_map[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    return -_eval(node.operand)
                if isinstance(node.op, ast.UAdd):
                    return +_eval(node.operand)
            if isinstance(node, ast.Call):
                return allowed_names[node.func.id](*[_eval(a) for a in node.args])
            raise ValueError("不支持的表达式")

        import operator as _operator

        operator_add = _operator.add
        operator_sub = _operator.sub
        operator_mul = _operator.mul
        operator_div = _operator.truediv
        operator_floordiv = _operator.floordiv
        operator_mod = _operator.mod
        operator_pow = _operator.pow

        result = _eval(tree.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return result

    @classmethod
    async def _fetch_battery_info(cls) -> dict:
        """获取底层真实硬件电池状态，优先调用 Termux:API"""
        candidates = [
            shutil.which("termux-battery-status"),
            "/data/data/com.termux/files/usr/bin/termux-battery-status",
            "/mnt/termux-home/../usr/bin/termux-battery-status",
        ]
        valid_cmds = []
        for c in candidates:
            if c and os.path.exists(c) and c not in valid_cmds:
                valid_cmds.append(c)

        for cmd in valid_cmds:
            try:
                proc = await asyncio.create_subprocess_exec(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=4.0)
                if stdout:
                    data = json.loads(stdout.decode("utf-8", errors="ignore"))
                    if isinstance(data, dict) and ("percentage" in data or "level" in data):
                        if "percentage" not in data and "level" in data:
                            data["percentage"] = data["level"]
                        return data
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[EchoTools] 调用 {cmd} 获取电量失败: {e}")

        # 次级回退：检查是否有本地持久化缓存文件
        for bpath in (Path("/sdcard/battery.json"), Path("/data/data/com.termux/files/home/battery.json")):
            try:
                if bpath.exists():
                    data = json.loads(bpath.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "percentage" in data:
                        return data
            except Exception:
                pass
        return {}

    @filter.command("电量")
    async def battery_command(self, event: AstrMessageEvent):
        """查询手机当前真实电量、充电状态、电池温度与健康度。"""
        info = await self._fetch_battery_info()
        if not info or "percentage" not in info:
            yield event.plain_result("❌ 暂时无法获取手机电池状态，请确认 Termux:API 运行正常。")
            return

        pct = info.get("percentage", 0)
        status_raw = str(info.get("status", "")).upper()
        plugged_raw = str(info.get("plugged", "")).upper()
        temp = float(info.get("temperature", 0.0) or 0.0)
        health_raw = str(info.get("health", "")).upper()
        voltage = float(info.get("voltage", 0) or 0) / 1000.0

        if "CHARGING" in status_raw and "NOT" not in status_raw and "DIS" not in status_raw:
            st_text = "⚡ 充电中"
        elif "FULL" in status_raw:
            st_text = "✨ 已充满"
        else:
            st_text = "🔋 电池供电 (放电中)"

        if "AC" in plugged_raw:
            plug_text = "电源适配器 (AC)"
        elif "USB" in plugged_raw:
            plug_text = "USB 数据线供电"
        elif "WIRELESS" in plugged_raw:
            plug_text = "无线充电"
        else:
            plug_text = "未插充电线"

        health_map = {
            "GOOD": "良好 (Good)",
            "OVERHEAT": "⚠️ 过热 (Overheat)",
            "DEAD": "❌ 损坏",
            "OVER_VOLTAGE": "⚠️ 过压",
        }
        health_text = health_map.get(health_raw, health_raw or "正常")
        temp_warn = " 🔥 偏热" if temp > 42.0 else " (温控良好)"

        current_raw = info.get("current", 0)
        current_ma = abs(int(current_raw or 0)) / 1000.0 if current_raw else 0
        current_str = f"\n• 实时电流：{current_ma:.0f} mA" if current_ma > 0 else ""

        msg = (
            f"🔋 【Echo 硬件状态与电量报告】\n"
            f"• 剩余电量：{pct}% ({st_text})\n"
            f"• 供电来源：{plug_text}\n"
            f"• 电池温度：{temp:.1f} °C{temp_warn}\n"
            f"• 电池健康：{health_text}\n"
            f"• 电池电压：{voltage:.2f} V{current_str}\n"
            f"• 运行模式：24h 移动常驻服务"
        )
        yield event.plain_result(msg)

    @filter.llm_tool(name="get_battery_status")
    async def get_battery_status(self, event: AstrMessageEvent) -> str:
        """获取手机当前真实电池电量百分比、充电状态与温度。当用户询问手机还有多少电、是否在充电、发热情况时调用。"""
        info = await self._fetch_battery_info()
        if not info or "percentage" not in info:
            return "无法获取电池信息"
        return (
            f"当前电量: {info.get('percentage')}%, "
            f"充电状态: {info.get('status')}, "
            f"供电方式: {info.get('plugged')}, "
            f"电池温度: {info.get('temperature')}°C, "
            f"电池健康: {info.get('health')}, "
            f"电压: {info.get('voltage')}mV"
        )



    @classmethod
    def _export_companion_tasks(cls) -> None:
        try:
            daily_dir = Path("/root/obsidiangit/2. Areas/日记")
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
                "focus": tasks
            }
            out_file = Path("/mnt/termux-home/echo_companion/tasks.json")
            out_file.parent.mkdir(parents=True, exist_ok=True)
            out_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"[EchoTools] 导出桌面待办失败: {exc}")


EchoTools._patch_openai_token_interceptor()

EchoTools._patch_openai_token_interceptor()
