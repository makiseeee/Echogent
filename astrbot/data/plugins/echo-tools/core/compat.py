"""AstrBot 运行期依赖兼容层与独立单测 Mock 垫片。"""

from __future__ import annotations

import logging
from typing import Any

# 1. Logger 垫片
try:
    from astrbot.api import logger
except ImportError:
    logger = logging.getLogger("echo-tools")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

# 2. 核心类与装饰器垫片 (单测离线运行时可用)
try:
    from astrbot.api.event import AstrMessageEvent, filter
    from astrbot.api.provider import ProviderRequest
    from astrbot.api.star import Context, Star, register
except ImportError:
    class AstrMessageEvent:
        def __init__(self, message_str: str = "", sender_id: str = "1249403130") -> None:
            self.message_str = message_str
            self._sender_id = sender_id
            self.unified_msg_origin = f"echo-qq:FriendMessage:{sender_id}"

        def get_sender_id(self) -> str:
            return self._sender_id

        def get_group_id(self) -> str | None:
            return None

        def plain_result(self, text: str) -> Any:
            return text

    class ProviderRequest:
        def __init__(self, prompt: str = "", system_prompt: str = "") -> None:
            self.prompt = prompt
            self.system_prompt = system_prompt
            self.audio_urls: list[str] = []
            self.extra_user_content_parts: list[Any] = []
            self.tool_calls_result: Any = None
            self.model: str = ""

    class Context:
        def __init__(self) -> None:
            self.cron_manager = None
            self.provider_manager = None
            self.platform_manager = None

    class Star:
        def __init__(self, context: Any = None) -> None:
            self.context = context

    class _FilterMock:
        @staticmethod
        def command(*args: Any, **kwargs: Any):
            def dec(fn: Any):
                return fn
            return dec

        @staticmethod
        def llm_tool(*args: Any, **kwargs: Any):
            def dec(fn: Any):
                return fn
            return dec

        @staticmethod
        def on_llm_request(*args: Any, **kwargs: Any):
            def dec(fn: Any):
                return fn
            return dec

        @staticmethod
        def on_decorating_result(*args: Any, **kwargs: Any):
            def dec(fn: Any):
                return fn
            return dec

    filter = _FilterMock()

    def register(*args: Any, **kwargs: Any):
        def dec(cls: Any):
            return cls
        return dec

try:
    from astrbot.core.provider.entities import TextPart
except ImportError:
    class TextPart:
        def __init__(self, text: str) -> None:
            self.text = text

        def mark_as_temp(self) -> TextPart:
            return self

__all__ = [
    "AstrMessageEvent",
    "Context",
    "ProviderRequest",
    "Star",
    "TextPart",
    "filter",
    "logger",
    "register",
]
