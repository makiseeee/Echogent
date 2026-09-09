import asyncio
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any
import unittest
from unittest.mock import AsyncMock, patch

plugin_path = Path(__file__).resolve().parent.parent / "astrbot" / "data" / "plugins" / "echo-tools"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from core.compat import Context
from core.config import PluginConfig
from core.event_bus import (
    BatteryEvent,
    EventBus,
    HUDNoticeEvent,
    PCActivityEvent,
    PrivateNoticeEvent,
    default_bus,
)
from sentries.battery_sentry import BatterySentry
from sentries.companion_hud import CompanionHUD
from sentries.mind_arbiter import MindArbiter
from sentries.pc_prober import PCProber
from sentries.supervisor import SentrySupervisor


class TestEventBusCore(unittest.IsolatedAsyncioTestCase):
    """EventBus 核心功能与异步并发单元测试。"""

    def setUp(self):
        self.bus = EventBus()

    async def test_sync_and_async_handlers(self):
        sync_results = []
        async_results = []

        def sync_h(ev: BatteryEvent):
            sync_results.append(ev.percentage)

        async def async_h(ev: BatteryEvent):
            await asyncio.sleep(0.01)
            async_results.append(ev.percentage)

        self.bus.subscribe(BatteryEvent, sync_h)
        self.bus.subscribe(BatteryEvent, async_h)

        await self.bus.publish(BatteryEvent(percentage=88, is_charging=True))

        self.assertEqual(sync_results, [88])
        self.assertEqual(async_results, [88])

    async def test_unsubscribe(self):
        results = []

        def handler(ev: BatteryEvent):
            results.append(ev.percentage)

        unsub = self.bus.subscribe(BatteryEvent, handler)
        await self.bus.publish(BatteryEvent(percentage=90, is_charging=False))
        self.assertEqual(results, [90])

        unsub()
        await self.bus.publish(BatteryEvent(percentage=45, is_charging=False))
        self.assertEqual(results, [90])

    async def test_class_inheritance_matching(self):
        class SpecializedBatteryEvent(BatteryEvent):
            pass

        received = []

        def base_handler(ev: BatteryEvent):
            received.append(ev.percentage)

        self.bus.subscribe(BatteryEvent, base_handler)

        # 发布子类事件，基类订阅者应当接收到
        await self.bus.publish(SpecializedBatteryEvent(percentage=77, is_charging=True))
        self.assertEqual(received, [77])

    async def test_exception_isolation(self):
        success_calls = []

        def bad_sync(ev: Any):
            raise RuntimeError("Sync fault")

        async def bad_async(ev: Any):
            raise RuntimeError("Async fault")

        def good_sync(ev: Any):
            success_calls.append("good_sync")

        async def good_async(ev: Any):
            await asyncio.sleep(0.01)
            success_calls.append("good_async")

        self.bus.subscribe(BatteryEvent, bad_sync)
        self.bus.subscribe(BatteryEvent, good_sync)
        self.bus.subscribe(BatteryEvent, bad_async)
        self.bus.subscribe(BatteryEvent, good_async)

        # 即使两个异常 handler 报错，正常 handler 依然执行且不向外抛出未捕获异常
        await self.bus.publish(BatteryEvent(percentage=50, is_charging=False))

        self.assertIn("good_sync", success_calls)
        self.assertIn("good_async", success_calls)

    async def test_clear_subscribers(self):
        results = []
        self.bus.subscribe(BatteryEvent, lambda ev: results.append(ev.percentage))
        self.bus.clear()

        await self.bus.publish(BatteryEvent(percentage=100, is_charging=True))
        self.assertEqual(results, [])


class TestSentryEventBusIntegration(unittest.IsolatedAsyncioTestCase):
    """哨兵组件与 EventBus 协同集成测试。"""

    def setUp(self):
        self.bus = EventBus()

    async def test_battery_sentry_publishes_events(self):
        sentry = BatterySentry(bus=self.bus)
        events_received = []

        self.bus.subscribe(BatteryEvent, lambda ev: events_received.append(ev))
        private_notices = []
        hud_notices = []
        self.bus.subscribe(PrivateNoticeEvent, lambda ev: private_notices.append(ev.text))
        self.bus.subscribe(HUDNoticeEvent, lambda ev: hud_notices.append(ev.text))

        fake_info = {
            "percentage": 10,
            "status": "DISCHARGING",
            "plugged": "UNPLUGGED",
            "temperature": 36.5,
            "voltage": 3.8,
        }

        with patch.object(BatterySentry, "fetch_battery_info", AsyncMock(return_value=fake_info)):
            with patch("asyncio.sleep", AsyncMock(side_effect=asyncio.CancelledError)):
                try:
                    await sentry.background_monitor_loop()
                except asyncio.CancelledError:
                    pass

        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0].percentage, 10)
        self.assertFalse(events_received[0].is_charging)
        self.assertTrue(events_received[0].is_critical)

        # 检查是否触发了双端告警事件
        self.assertTrue(len(private_notices) > 0)
        self.assertTrue(len(hud_notices) > 0)
        self.assertIn("10%", private_notices[0])

    async def test_mind_arbiter_reacts_to_events(self):
        mock_ctx = AsyncMock()
        arbiter = MindArbiter(context=mock_ctx, bus=self.bus)
        arbiter.check_ambient_dark = AsyncMock(return_value=False)
        arbiter.generate_mind_speech = AsyncMock(return_value="充电测试对白\n(=ﾟωﾟ)=")

        dispatched_hud = []
        dispatched_private = []
        self.bus.subscribe(HUDNoticeEvent, lambda ev: dispatched_hud.append(ev.text))
        self.bus.subscribe(PrivateNoticeEvent, lambda ev: dispatched_private.append(ev.text))

        arbiter.start_listening()

        # 1. 模拟未插电状态
        arbiter.last_charging_state = False

        # 2. 模拟插上充电器事件
        await self.bus.publish(BatteryEvent(percentage=40, is_charging=True))

        self.assertEqual(arbiter.last_charging_state, True)
        self.assertEqual(len(dispatched_hud), 1)
        self.assertIn("充电测试对白", dispatched_hud[0])
        self.assertEqual(len(dispatched_private), 1)

        arbiter.stop_listening()

    async def test_supervisor_wiring_and_lifecycle(self):
        mock_ctx = AsyncMock()
        config = PluginConfig()
        supervisor = SentrySupervisor(mock_ctx, config, bus=self.bus)

        self.assertEqual(supervisor.battery.bus, self.bus)
        self.assertEqual(supervisor.pc.bus, self.bus)
        self.assertEqual(supervisor.mind.bus, self.bus)

        # 测试通过总线发送 HUD 和 Private 告警
        hud_mock = AsyncMock()
        private_mock = AsyncMock()
        supervisor.hud.push_bubble = hud_mock
        supervisor.send_private_notice = private_mock

        with patch.object(CompanionHUD, "export_companion_tasks_async", AsyncMock()):
            with patch.object(supervisor.pc, "background_prober_loop", AsyncMock()):
                with patch.object(supervisor.battery, "background_monitor_loop", AsyncMock()):
                    with patch.object(supervisor.mind, "background_mind_arbiter_loop", AsyncMock()):
                        await supervisor.start_all()

                        await self.bus.publish(HUDNoticeEvent(text="测试气泡", motion=2))
                        await self.bus.publish(PrivateNoticeEvent(text="测试私信"))

                        hud_mock.assert_awaited_once_with("测试气泡", 2)
                        private_mock.assert_awaited_once_with("测试私信")

                        await supervisor.stop_all()

                        self.assertEqual(len(supervisor._unsubs), 0)


if __name__ == "__main__":
    unittest.main()
