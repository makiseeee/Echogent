"""全局 OpenAI / SiliconFlow API Token 拦截与双币种账本记录器。"""

from __future__ import annotations

from datetime import datetime, timezone
import functools
import os
from pathlib import Path
import sqlite3
from typing import Any

from core.compat import logger


class TokenInterceptor:
    """挂载到 OpenAI AsyncCompletions.create 上的全局 Token 拦截器。"""

    _patched: bool = False

    @staticmethod
    def ensure_database(db_path: Path) -> None:
        """初始化或升级用量记录 SQLite 数据库。"""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path, timeout=10.0) as db:
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

    @classmethod
    def install(cls, db_path: Path) -> None:
        """全局 Hook OpenAI AsyncCompletions.create。"""
        if cls._patched:
            return
        cls.ensure_database(db_path)
        try:
            from openai.resources.chat.completions import AsyncCompletions

            orig_create = AsyncCompletions.create

            @functools.wraps(orig_create)
            async def wrapped_create(*args: Any, **kwargs: Any) -> Any:
                is_stream = kwargs.get("stream", False)
                resp = await orig_create(*args, **kwargs)
                if not is_stream:
                    cls.record_api_usage(db_path, resp)
                    return resp

                async def wrapped_stream():
                    captured = False
                    async for chunk in resp:
                        if not captured and hasattr(chunk, "usage") and chunk.usage:
                            u = chunk.usage
                            p_tok = getattr(u, "prompt_tokens", 0) or 0
                            c_tok = getattr(u, "completion_tokens", 0) or 0
                            if p_tok > 0 or c_tok > 0:
                                cls.record_api_usage(db_path, chunk)
                                captured = True
                        yield chunk

                return wrapped_stream()

            AsyncCompletions.create = wrapped_create
            cls._patched = True
            logger.info("[TokenInterceptor] 全局 OpenAI/SiliconFlow API Token 拦截器挂载成功。")
        except (ImportError, ModuleNotFoundError):
            logger.info("[TokenInterceptor] 未检测到 openai 模块，跳过全局 API 拦截器挂载。")
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"[TokenInterceptor] 挂载全局 Token 拦截器失败: {exc}")

    @staticmethod
    def estimate_cost(
        model: str,
        input_other: int,
        input_cached: int,
        output: int,
        created_at: datetime | None = None,
    ) -> float:
        """
        按 Command Code 官方 Go 计划费率计算美元成本 (USD)。
        参考文档: https://commandcode.ai/docs/plans/go (单位: $ / 1M tokens)
        """
        normalized = model.lower()
        now_dt = created_at or datetime.now(timezone.utc)
        utc_hour = now_dt.hour
        # Command Code 峰值时段: 01:00-04:00 & 06:00-10:00 UTC (每日共 7 小时)
        is_peak = (1 <= utc_hour < 4) or (6 <= utc_hour < 10)

        # 1. DeepSeek V4 Flash Fast (当前主力，固定阶梯，无高峰期溢价)
        if "flash-fast" in normalized or "flash_fast" in normalized:
            rate_in, rate_cached, rate_out = 0.28, 0.07, 0.56

        # 2. DeepSeek V4 Flash / Vision (标准版，分高峰/平峰)
        elif "v4-flash" in normalized or "v4_flash" in normalized or ("deepseek-v4" in normalized and "pro" not in normalized):
            if is_peak:
                rate_in, rate_cached, rate_out = 0.44, 0.014, 1.32
            else:
                rate_in, rate_cached, rate_out = 0.22, 0.007, 0.66

        # 3. DeepSeek V4 Pro (分高峰/平峰)
        elif "v4-pro" in normalized or "v4_pro" in normalized:
            if is_peak:
                rate_in, rate_cached, rate_out = 1.32, 0.044, 3.96
            else:
                rate_in, rate_cached, rate_out = 0.66, 0.022, 1.98

        # 4. 通用 DeepSeek
        elif "deepseek" in normalized:
            rate_in, rate_cached, rate_out = 0.28, 0.07, 0.56

        # 5. GLM 系列 (智谱 / Z-AI)
        elif "glm-5.3-flash" in normalized or ("glm-5" in normalized and "flash" in normalized):
            rate_in, rate_cached, rate_out = 0.15, 0.03, 0.50
        elif "glm-4" in normalized:
            rate_in, rate_cached, rate_out = 0.10, 0.02, 0.10
        elif "glm" in normalized:
            rate_in, rate_cached, rate_out = 1.40, 0.26, 4.40

        # 6. Qwen 系列
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

        return (input_other * rate_in + input_cached * rate_cached + output * rate_out) / 1_000_000

    @classmethod
    def record_api_usage(cls, db_path: Path, completion_obj: Any) -> None:
        """将一次 API Completion 的消耗精准写入 usage 表。"""
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
            cost_usd = cls.estimate_cost(model, input_other, input_cached, output)
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
            logger.error(f"[TokenInterceptor] 记录 Token 用量失败: {e}")
