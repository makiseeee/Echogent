"""手机电池硬件状态监控与低电量双端预警哨兵 (BatterySentry)。"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
import json
import os
from pathlib import Path
import shutil
from typing import Any

from core.compat import logger
from core.event_bus import (
    BatteryEvent,
    EventBus,
    HUDNoticeEvent,
    PrivateNoticeEvent,
    default_bus,
)


class BatterySentry:
    """监测手机硬件电池电量、温度与充放电状态。"""

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or default_bus
        self.battery_low_alerted = False
        self.battery_critical_alerted = False

    @staticmethod
    async def fetch_battery_info() -> dict[str, Any]:
        """获取真实硬件电池状态，优先调用 Termux:API。"""
        candidates = [
            shutil.which("termux-battery-status"),
            "/data/data/com.termux/files/usr/bin/termux-battery-status",
            "/mnt/termux-home/../usr/bin/termux-battery-status",
        ]
        valid_cmds = [c for c in candidates if c and os.path.exists(c)]

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
                logger.debug(f"[BatterySentry] 调用 {cmd} 获取电量失败: {e}")

        # 次级回退：读取本地持久化缓存文件
        for bpath in (Path("/sdcard/battery.json"), Path("/data/data/com.termux/files/home/battery.json")):
            try:
                if bpath.exists():
                    data = json.loads(bpath.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "percentage" in data:
                        return data
            except Exception:
                pass
        return {}

    @classmethod
    def format_command_report(cls, info: dict[str, Any]) -> str:
        """为 /电量 指令格式化人类可读的详细电量报告。"""
        if not info or "percentage" not in info:
            return "❌ 暂时无法获取手机电池状态，请确认 Termux:API 运行正常。"

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

        return (
            f"🔋 【Echo 硬件状态与电量报告】\n"
            f"• 剩余电量：{pct}% ({st_text})\n"
            f"• 供电来源：{plug_text}\n"
            f"• 电池温度：{temp:.1f} °C{temp_warn}\n"
            f"• 电池健康：{health_text}\n"
            f"• 电池电压：{voltage:.2f} V{current_str}\n"
            f"• 运行模式：24h 移动常驻服务"
        )

    @classmethod
    def format_tool_status(cls, info: dict[str, Any]) -> str:
        """为 LLM Tool get_battery_status 格式化摘要字符串。"""
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

    async def background_monitor_loop(
        self,
        send_notice_func: Callable[[str], Coroutine[Any, Any, None]] | None = None,
        push_bubble_func: Callable[[str, int], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        """后台低功耗电池状态守护：低电量主动双端告警并发布 BatteryEvent。"""
        while True:
            try:
                info = await self.fetch_battery_info()
                pct = info.get("percentage") if info else None
                status_raw = str(info.get("status", "")).upper() if info else ""
                plugged_raw = str(info.get("plugged", "")).upper() if info else ""
                is_charging = (
                    ("CHARGING" in status_raw and "NOT" not in status_raw and "DIS" not in status_raw)
                    or "AC" in plugged_raw
                    or "USB" in plugged_raw
                    or "WIRELESS" in plugged_raw
                )

                # 向总线发布全量电池状态事件
                await self.bus.publish(
                    BatteryEvent(
                        percentage=int(pct or 0),
                        is_charging=is_charging,
                        plugged=plugged_raw,
                        temperature=float(info.get("temperature", 0.0)) if info else 0.0,
                        voltage=float(info.get("voltage", 0.0)) if info else 0.0,
                        is_low=pct is not None and pct <= 20 and not is_charging,
                        is_critical=pct is not None and pct <= 10 and not is_charging,
                    )
                )

                if is_charging or (pct is not None and pct >= 30):
                    self.battery_low_alerted = False
                    self.battery_critical_alerted = False
                elif pct is not None and not is_charging:
                    if pct <= 10 and not self.battery_critical_alerted:
                        msg = (
                            f"wenbo！电量只剩 {pct}% 了！真的快要撑不住关机了…\n"
                            f"赶紧救命充电 (つД`)"
                        )
                        bubble = f"电量仅剩 {pct}%，快充充电！"
                        await self.bus.publish(PrivateNoticeEvent(text=msg))
                        await self.bus.publish(HUDNoticeEvent(text=bubble, motion=5))
                        if send_notice_func:
                            await send_notice_func(msg)
                        if push_bubble_func:
                            await push_bubble_func(bubble, 5)
                        self.battery_critical_alerted = True
                        self.battery_low_alerted = True
                    elif pct <= 20 and not self.battery_low_alerted:
                        msg = (
                            f"wenbo，电量只剩 {pct}% 了…\n"
                            f"快点给我插上充电线啦，不然等下关机了我可不管你 (；´д｀)"
                        )
                        bubble = f"电量剩 {pct}% 啦，快插上线~"
                        await self.bus.publish(PrivateNoticeEvent(text=msg))
                        await self.bus.publish(HUDNoticeEvent(text=bubble, motion=3))
                        if send_notice_func:
                            await send_notice_func(msg)
                        if push_bubble_func:
                            await push_bubble_func(bubble, 3)
                        self.battery_low_alerted = True

                # 未插电且低电量时，加密轮询；充电中或正常电量时，低频 10 分钟检测
                sleep_sec = 180 if (not is_charging and pct is not None and pct <= 25) else 600
                await asyncio.sleep(sleep_sec)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[BatterySentry] battery monitor loop error: {exc}")
                await asyncio.sleep(60)
