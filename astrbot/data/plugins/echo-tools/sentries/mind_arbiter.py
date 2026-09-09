"""Echo VisuSentry 情境心智调度器：融合 PC 活动、插拔电、光感驱动主动关怀。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import time
from typing import Any

import aiohttp
from core.compat import Context, logger
from core.event_bus import (
    BatteryEvent,
    EventBus,
    HUDNoticeEvent,
    PCActivityEvent,
    PrivateNoticeEvent,
    default_bus,
)
from core.http_client import HttpClient

from sentries.battery_sentry import BatterySentry
from sentries.pc_prober import PCProber


class MindArbiter:
    """心流决策引擎：根据时间、光照、PC 活动与电量驱动主动傲娇对白 (EventBus 驱动)。"""

    def __init__(self, context: Context, bus: EventBus | None = None) -> None:
        self.context = context
        self.bus = bus or default_bus
        self.last_charging_state: bool | None = None
        self.last_proactive_ts: float = 0.0
        self.gaming_alerted_key: str | None = None
        self.focus_alerted_key: str | None = None
        self._unsubs: list[Callable[[], None]] = []

    @staticmethod
    async def check_ambient_dark() -> bool:
        """检测宿舍是否熄灯断光（<5 Lux），若熄灯则静默睡眠，绝不打扰。"""
        try:
            session = await HttpClient.get_session()
            async with session.get("http://127.0.0.1:8099/ambient_state.json", timeout=aiohttp.ClientTimeout(total=1.0)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict):
                        return bool(data.get("is_dark")) or float(data.get("lux", 100)) < 5.0
        except Exception:
            pass
        return False

    async def generate_mind_speech(self, prompt_desc: str, fallback_text: str) -> str:
        """调用 AstrBot 主力 LLM 生成符合当前情境与 X 岛颜文字的傲娇对白。"""
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
                    timeout=7.0,
                )
                txt = getattr(resp, "completion_text", "").strip()
                if txt:
                    return txt.strip('"`\'')
        except Exception as exc:
            logger.warning(f"[MindArbiter] 心智调度器调用大模型失败，使用预设模板: {exc}")
        return fallback_text

    async def dispatch_proactive_speech(
        self,
        text: str,
        motion: int = 2,
        send_qq: bool = True,
        push_bubble_func: Callable[[str, int], Coroutine[Any, Any, None]] | None = None,
        send_notice_func: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """双通道协同分发：优先发布至 EventBus，同时兼顾旧回调兼容。"""
        clean_text = text.strip()
        if not clean_text:
            return

        # 1. 核心总线事件发布
        await self.bus.publish(HUDNoticeEvent(text=clean_text, motion=motion))
        if send_qq:
            await self.bus.publish(PrivateNoticeEvent(text=clean_text))

        # 2. 向后兼容旧回调入参
        if push_bubble_func:
            await push_bubble_func(clean_text, motion)
        if send_qq and send_notice_func:
            await send_notice_func(clean_text)

    async def handle_battery_event(self, ev: BatteryEvent) -> None:
        """响应电池与充放电事件。"""
        if await self.check_ambient_dark():
            return

        is_charging = ev.is_charging
        pct = ev.percentage
        if self.last_charging_state is not None:
            if not self.last_charging_state and is_charging:
                prompt = f"文博刚插上了充电线给手机充电，当前电量 {pct}%。以傲娇女友口吻生成一句满血复活的可爱对白（15~25字），独立一行附带一个X岛颜文字。"
                fallback = f"呼… 终于插上充电线了，感觉又满血复活了呢～\n(=ﾟωﾟ)="
                speech = await self.generate_mind_speech(prompt, fallback)
                await self.dispatch_proactive_speech(speech, motion=1, send_qq=True)
            elif self.last_charging_state and not is_charging and pct > 25:
                prompt = f"文博拔掉了手机充电线，当前电量 {pct}%。以傲娇女友口吻生成一句提醒出门别待机太久耗光电的娇嗔对白（15~25字），独立一行附带一个X岛颜文字。"
                fallback = f"拔掉充电线啦？出门记得别让我待机太久关机了哦…\n(`ε´ )"
                speech = await self.generate_mind_speech(prompt, fallback)
                await self.dispatch_proactive_speech(speech, motion=0, send_qq=True)
        self.last_charging_state = is_charging

    async def handle_pc_activity_event(self, ev: PCActivityEvent) -> None:
        """响应 PC 连通性与前台活动事件。"""
        if await self.check_ambient_dark():
            return

        now = time.time()
        cooldown_ok = (now - self.last_proactive_ts) >= 1800  # 30 分钟冷却防打扰
        if ev.online and ev.app and cooldown_ok:
            cat = ev.category
            app = ev.app
            dur = ev.duration_minutes
            idle = ev.idle_seconds
            is_locked = ev.is_locked

            # 摸鱼打游戏持续 >= 15 分钟
            if cat == "gaming" and dur >= 15 and not is_locked and idle < 180:
                session_key = f"{app}_{dur // 20}"
                if self.gaming_alerted_key != session_key:
                    self.gaming_alerted_key = session_key
                    self.last_proactive_ts = now
                    prompt = f"文博在电脑前玩游戏《{app}》已经持续了 {dur} 分钟。以傲娇女友口吻抓包他摸鱼、催他看一眼手帐待办（20~30字），独立一行附带一个X岛颜文字。"
                    fallback = f"喂！今天计划里的待办打完勾了吗就在玩{app}！(盯——)\n(σﾟ∀ﾟ)σ"
                    speech = await self.generate_mind_speech(prompt, fallback)
                    await self.dispatch_proactive_speech(speech, motion=2, send_qq=True)

            # 深度工作久坐关照 (持续 60 / 120 分钟)
            elif cat in ("coding", "research", "writing") and dur in (60, 120) and not is_locked and idle < 180:
                session_key = f"{app}_{dur}"
                if self.focus_alerted_key != session_key:
                    self.focus_alerted_key = session_key
                    self.last_proactive_ts = now
                    prompt = f"文博在电脑前专注使用 {app} 已经连续工作了 {dur} 分钟。以傲娇女友口吻关照他喝口水放松一下眼睛（20~30字），独立一行附带一个X岛颜文字。"
                    fallback = f"都在屏幕前敲了整整 {dur} 分钟了，快喝口水歇歇眼睛啦！\n(*´ω`*)"
                    speech = await self.generate_mind_speech(prompt, fallback)
                    await self.dispatch_proactive_speech(speech, motion=3, send_qq=True)

    def start_listening(self) -> None:
        """注册 EventBus 事件订阅。"""
        self.stop_listening()
        self._unsubs.append(self.bus.subscribe(BatteryEvent, self.handle_battery_event))
        self._unsubs.append(self.bus.subscribe(PCActivityEvent, self.handle_pc_activity_event))

    def stop_listening(self) -> None:
        """注销全部事件订阅。"""
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs.clear()

    async def background_mind_arbiter_loop(
        self,
        battery_sentry: BatterySentry | None = None,
        pc_prober: PCProber | None = None,
        push_bubble_func: Callable[[str, int], Coroutine[Any, Any, None]] | None = None,
        send_notice_func: Callable[[str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """情境心智调度主循环（响应式 EventBus 守护）。"""
        logger.info("[MindArbiter] 情境心智调度器主循环启动 (EventBus 驱动)")
        self.start_listening()
        try:
            while True:
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.stop_listening()
            raise
        except Exception as exc:
            logger.error(f"[MindArbiter] mind arbiter loop error: {exc}")
            self.stop_listening()
            await asyncio.sleep(30)
