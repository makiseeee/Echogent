"""后台感知守护监督器 (SentrySupervisor)：统一生命周期管理与异常隔离。"""

from __future__ import annotations

import asyncio
from typing import Any

from core.compat import Context, logger

from core.config import PluginConfig
from sentries.battery_sentry import BatterySentry
from sentries.companion_hud import CompanionHUD
from sentries.mind_arbiter import MindArbiter
from sentries.pc_prober import PCProber


class SentrySupervisor:
    """集中管理所有后台硬件与状态监控哨兵的生命周期。"""

    def __init__(self, context: Context, config: PluginConfig) -> None:
        self.context = context
        self.config = config
        self.battery = BatterySentry()
        self.pc = PCProber(config)
        self.hud = CompanionHUD()
        self.mind = MindArbiter(context)

        self.pc_task: asyncio.Task | None = None
        self.battery_task: asyncio.Task | None = None
        self.mind_task: asyncio.Task | None = None

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

    async def start_all(self) -> None:
        """启动所有后台哨兵任务。"""
        # 1. 导出当前桌面待办
        CompanionHUD.export_companion_tasks(self.config.vault_dir)

        # 2. 启动 PC 探针
        if self.pc_task is None or self.pc_task.done():
            self.pc_task = asyncio.create_task(self.pc.background_prober_loop())

        # 3. 启动电池监控
        if self.battery_task is None or self.battery_task.done():
            self.battery_task = asyncio.create_task(
                self.battery.background_monitor_loop(
                    send_notice_func=self.send_private_notice,
                    push_bubble_func=CompanionHUD.push_bubble,
                )
            )

        # 4. 启动情境心智调度器
        if self.mind_task is None or self.mind_task.done():
            self.mind_task = asyncio.create_task(
                self.mind.background_mind_arbiter_loop(
                    battery_sentry=self.battery,
                    pc_prober=self.pc,
                    push_bubble_func=CompanionHUD.push_bubble,
                    send_notice_func=self.send_private_notice,
                )
            )
        logger.info("[SentrySupervisor] 所有后台感知与协同守护已挂载完成。")

    async def stop_all(self) -> None:
        """平滑关停所有后台守护任务。"""
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
