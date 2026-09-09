"""后台感知守护监督器 (SentrySupervisor)：统一生命周期管理与异常隔离。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from core.compat import Context, logger

from core.config import PluginConfig
from core.event_bus import (
    EventBus,
    HUDNoticeEvent,
    PrivateNoticeEvent,
    default_bus,
)
from sentries.battery_sentry import BatterySentry
from sentries.companion_hud import CompanionHUD
from sentries.mind_arbiter import MindArbiter
from sentries.pc_prober import PCProber


class SentrySupervisor:
    """集中管理所有后台硬件与状态监控哨兵的生命周期。"""

    def __init__(self, context: Context, config: PluginConfig, bus: EventBus | None = None) -> None:
        self.context = context
        self.config = config
        self.bus = bus or default_bus
        self.battery = BatterySentry(bus=self.bus)
        self.pc = PCProber(config, bus=self.bus)
        self.hud = CompanionHUD()
        self.mind = MindArbiter(context, bus=self.bus)

        self.pc_task: asyncio.Task | None = None
        self.battery_task: asyncio.Task | None = None
        self.mind_task: asyncio.Task | None = None
        self._unsubs: list[Callable[[], None]] = []

    async def send_private_notice(self, text: str) -> None:
        """主动向用户 QQ 发送私聊系统/提醒消息。"""
        try:
            session = self.config.get_daily_cron_session()
            sender_id = session.rsplit(":", 1)[-1]
            pm = getattr(self.context, "platform_manager", None)
            platform_insts = getattr(pm, "platform_insts", []) if pm else []
            adapter = next(
                (
                    inst
                    for inst in platform_insts
                    if "qq" in str(getattr(inst, "platform_name", "")).lower()
                    or "aiocqhttp" in str(type(inst)).lower()
                ),
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
                logger.info(f"[SentrySupervisor] 已发送私信提醒给 {sender_id}: {text}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[SentrySupervisor] 发送私信提醒失败: {exc}")

    async def _on_hud_notice(self, ev: HUDNoticeEvent) -> None:
        await self.hud.push_bubble(ev.text, ev.motion)

    async def _on_private_notice(self, ev: PrivateNoticeEvent) -> None:
        await self.send_private_notice(ev.text)

    async def start_all(self) -> None:
        """启动所有后台哨兵任务并订阅事件总线。"""
        # 1. 导出当前桌面待办
        await CompanionHUD.export_companion_tasks_async(self.config.vault_dir)

        # 2. 注册总线监听
        if not self._unsubs:
            self._unsubs.append(self.bus.subscribe(HUDNoticeEvent, self._on_hud_notice))
            self._unsubs.append(self.bus.subscribe(PrivateNoticeEvent, self._on_private_notice))

        # 3. 启动 PC 探针
        if self.pc_task is None or self.pc_task.done():
            self.pc_task = asyncio.create_task(self.pc.background_prober_loop())

        # 4. 启动电池监控 (由 EventBus 驱动通知分发)
        if self.battery_task is None or self.battery_task.done():
            self.battery_task = asyncio.create_task(
                self.battery.background_monitor_loop()
            )

        # 5. 启动情境心智调度器 (由 EventBus 驱动事件流)
        if self.mind_task is None or self.mind_task.done():
            self.mind_task = asyncio.create_task(
                self.mind.background_mind_arbiter_loop()
            )
        logger.info("[SentrySupervisor] 所有后台感知与协同守护已挂载完成 (EventBus 驱动)。")

    async def stop_all(self) -> None:
        """平滑关停所有后台守护任务并注销事件订阅。"""
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:
                pass
        self._unsubs.clear()

        tasks = [self.pc_task, self.battery_task, self.mind_task]
        for t in tasks:
            if t is not None and not t.done():
                t.cancel()

        for t in tasks:
            if t is not None:
                try:
                    await t
                except asyncio.CancelledError:
                    pass

        self.pc_task = None
        self.battery_task = None
        self.mind_task = None
        logger.info("[SentrySupervisor] 所有后台感知守护已优雅停机。")
