"""轻量进程内异步发布/订阅事件总线 (EventBus)。

零第三方依赖，纯标准库 asyncio 与 dataclasses。
支持强类型事件类与字符串事件名，具备异常隔离保护与多订阅者并发派发能力。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import inspect
import logging
import time
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger("echo.event_bus")

T = TypeVar("T")
Handler = Callable[[Any], Coroutine[Any, Any, None] | None]


# ==========================================
# 核心事件数据模型 (Standard Events)
# ==========================================

@dataclass(frozen=True)
class BatteryEvent:
    """电池状态与充放电变化事件。"""
    percentage: int
    is_charging: bool
    plugged: str = ""
    temperature: float = 0.0
    voltage: float = 0.0
    is_low: bool = False
    is_critical: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PCActivityEvent:
    """PC 连通性与前台活动状态变更事件。"""
    online: bool
    app: str = ""
    category: str = ""
    window_title: str = ""
    duration_minutes: int = 0
    idle_seconds: int = 0
    is_locked: bool = False
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class HUDNoticeEvent:
    """桌面伴侣屏幕气泡展示事件。"""
    text: str
    motion: int = 0
    duration_seconds: int = 5
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class PrivateNoticeEvent:
    """向 Owner 发送私聊消息事件（如 QQ 私信告警/提醒）。"""
    text: str
    timestamp: float = field(default_factory=time.time)


# ==========================================
# 事件总线实现 (EventBus)
# ==========================================

class EventBus:
    """进程内轻量发布/订阅事件总线。"""

    def __init__(self) -> None:
        self._subscribers: dict[Any, list[Handler]] = {}

    def subscribe(
        self,
        event_type: type[T] | str,
        handler: Callable[[T], Coroutine[Any, Any, None] | None],
    ) -> Callable[[], None]:
        """订阅特定事件类型或事件名称，返回用于取消订阅的无参回调。"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)

        def unsubscribe() -> None:
            subs = self._subscribers.get(event_type, [])
            if handler in subs:
                subs.remove(handler)
            if not subs and event_type in self._subscribers:
                del self._subscribers[event_type]

        return unsubscribe

    async def publish(self, event: Any) -> None:
        """异步发布事件，并发派发给所有订阅者并提供异常隔离。"""
        handlers: list[Handler] = []

        if isinstance(event, type):
            ev_cls = event
        else:
            ev_cls = type(event)

        for subscribed_key, subs in list(self._subscribers.items()):
            if isinstance(subscribed_key, type) and issubclass(ev_cls, subscribed_key):
                handlers.extend(subs)
            elif isinstance(subscribed_key, str) and (
                subscribed_key == getattr(event, "name", None)
                or subscribed_key == ev_cls.__name__
            ):
                handlers.extend(subs)

        if not handlers:
            return

        tasks = []
        for h in handlers:
            try:
                res = h(event)
                if inspect.isawaitable(res):
                    tasks.append(asyncio.create_task(self._safe_invoke(h, res, event)))
            except Exception as exc:
                h_name = getattr(h, "__name__", str(h))
                logger.error(f"[EventBus] 同步处理器 {h_name} 处理 {ev_cls.__name__} 失败: {exc}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _safe_invoke(handler: Handler, coro: Coroutine[Any, Any, None], event: Any) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            h_name = getattr(handler, "__name__", str(handler))
            logger.error(f"[EventBus] 异步处理器 {h_name} 处理 {type(event).__name__} 失败: {exc}")

    def clear(self) -> None:
        """清空所有订阅（常用于测试重置）。"""
        self._subscribers.clear()


# 全局共享默认单例总线
default_bus = EventBus()
