"""PC 桌面活动探针、情境状态注入与网络唤醒 (PCProber)。"""

from __future__ import annotations

import asyncio
import socket
import time
from typing import Any

import aiohttp
from core.compat import ProviderRequest, logger

from core.config import PluginConfig


class PCProber:
    """负责 PC 在线探测、活动窗口采集、口语化转换与情境提示词注入。"""

    def __init__(self, config: PluginConfig) -> None:
        self.config = config
        self.online = False
        self.detail = ""
        self.activity: dict[str, Any] = {}
        self.last_probe_ts = 0.0

    async def probe_computer(self, timeout_sec: float = 2.0) -> tuple[bool, str]:
        """优先探测台式机 PC Agent，获取前台实时活动与状态。"""
        host = os.environ.get("ECHO_PC_AGENT_HOST", "10.144.232.236")
        port = int(os.environ.get("ECHO_PC_AGENT_PORT", "8766"))
        pc_agent_url = f"http://{host}:{port}/api/pc/activity?level=detail"
        token = os.environ.get("ECHO_PC_TOKEN", "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(pc_agent_url, headers=headers) as resp:
                    if resp.status == 200:
                        payload = await resp.json(content_type=None)
                        if isinstance(payload, dict) and (payload.get("status") == "online" or bool(payload.get("app"))):
                            self.online = True
                            self.activity = payload
                            self.last_probe_ts = time.time()
                            app = payload.get("app", "")
                            summary = payload.get("summary", "")
                            self.detail = f"{app} ({summary})"
                            return True, self.detail
        except Exception as exc:
            logger.debug(f"[PCProber] 探测 PC Agent 异常: {exc}")

        # 若 PC Agent 暂未响应，尝试回落至传统 MCP 服务检测
        try:
            url, authorization = self.config.get_obsidian_connection()
            url = url.replace("/obsidian", "/status")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_sec)) as session:
                async with session.get(url, headers={"Authorization": authorization}) as resp:
                    payload = await resp.json(content_type=None)
            mcp_online = resp.status == 200 and bool(payload.get("online"))
            caps = payload.get("capabilities", [])
            mcp_detail = "、".join(caps) if mcp_online else ""
        except Exception:
            mcp_online, mcp_detail = False, ""

        # 仅在超过 60 秒未成功取得 PC 状态时才判定离线并清空活动
        if time.time() - self.last_probe_ts > 60:
            self.online = mcp_online
            self.detail = mcp_detail
            if not mcp_online:
                self.activity = {}
        return self.online, self.detail

    async def background_prober_loop(self) -> None:
        """静默后台心跳：在线 20 秒、离线 35 秒探测一次 PC 状态。"""
        while True:
            try:
                await self.probe_computer(timeout_sec=2.0)
                await asyncio.sleep(20 if self.online else 35)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error(f"[PCProber] background computer prober error: {exc}")
                await asyncio.sleep(30)

    @staticmethod
    def humanize_pc_activity(act: dict[str, Any]) -> str:
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

    def inject_status_to_prompt(
        self,
        req: ProviderRequest,
        user_msg: str,
        text_part_cls: Any = None,
    ) -> None:
        """根据文博输入意图分级（A 询问、B 疲惫、C 闲聊背景），注入情境提示词。"""
        user_msg_lower = user_msg.lower()

        if self.online and self.activity:
            act = self.activity
            dur = act.get("duration_minutes", 0)
            human_act = self.humanize_pc_activity(act)

            inquiry_kws = ["猜猜我在", "猜猜我", "我在干嘛", "我在做什么", "看我干嘛", "你看我干嘛", "你在看我吗", "看我在", "知道我在", "猜猜"]
            is_inquiry = any(kw in user_msg_lower for kw in inquiry_kws)

            fatigue_kws = ["好累", "累死", "头疼", "头大", "脖子酸", "写不出来", "调不通", "好烦", "烦死", "不想写了", "改不动", "困死"]
            is_fatigue = any(kw in user_msg_lower for kw in fatigue_kws)

            if is_inquiry:
                status = (
                    f"【实时感知交互指令 · 文博主动询问自己在干嘛】：\n"
                    f"你通过桌面伴侣端实时感知到文博当前正在电脑前【{human_act}】"
                    + (f"（已专注持续 {dur} 分钟）" if dur > 1 else "") + "。\n"
                    f"请用你傲娇、嘴硬心软的女友口吻直接调侃他（例如指出他电脑正开着呢、当我看不见/当我瞎呀、少让我猜了等），"
                    f"用口语化的词（如“{human_act}”），严禁机械背诵冗长窗口标题！严禁说你不知道或瞎猜他刚睡醒！"
                )
            elif is_fatigue:
                status = (
                    f"【实时情境感知 · 情绪共情】：\n"
                    f"感知到文博在电脑前【{human_act}】已有 {dur} 分钟。\n"
                    f"他在向你倾诉疲累或烦躁。请用你表面嫌弃嘴硬、实则心疼关切的女友口吻回应他，"
                    f"可以自然地催他起来喝水、活动活动脖子或休息一下，严禁生硬背诵窗口全称。"
                )
            else:
                status = (
                    f"【实时物理与环境潜意识背景（严禁在回复中主动提及）】：\n"
                    f"文博当前在电脑前（{human_act}）。\n"
                    f"【绝对铁律】：文博正在与你进行普通日常闲聊（非询问在干嘛，也未表达疲惫）。"
                    f"请将此情境完全作为内隐潜意识背景，严禁在回复中主动报幕或突兀提及他在开什么软件、在干什么！专注于回答文博当前聊的话题本身。"
                )

            logger.info(f"[PCProber] 注入桌面情境[inquiry={is_inquiry}, fatigue={is_fatigue}]: act={human_act}")

            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"
            else:
                req.system_prompt = status

            if text_part_cls is not None and is_inquiry:
                req.extra_user_content_parts.append(text_part_cls(text=f"[情境指引] {status}").mark_as_temp())
        elif self.online:
            status = f"【桌面情境】电脑在线（{self.detail}）。普通闲聊时保持静默背景。"
            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"
        else:
            status = "【桌面情境潜意识】电脑当前离线或休眠锁屏，文博未在电脑前。若他让你猜他在干嘛，可调侃他电脑都没开、是不是在抱着手机摸鱼。"
            if req.system_prompt:
                req.system_prompt = f"{req.system_prompt.strip()}\n\n{status}\n"

    @classmethod
    def send_wol(cls, mac: str | None = None) -> tuple[bool, str]:
        """局域网唤醒台式机：广播 WOL Magic Packet。"""
        target_mac = mac or os.environ.get("ECHO_PC_MAC", "B0-25-AA-59-A9-27")
        bcast_ip = os.environ.get("ECHO_PC_WOL_BCAST", "100.67.255.255")
        try:
            mac_bytes = bytes.fromhex(target_mac.replace(":", "").replace("-", ""))
            magic = b"\xff" * 6 + mac_bytes * 16
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                for bcast in (bcast_ip, "255.255.255.255"):
                    try:
                        s.sendto(magic, (bcast, 9))
                    except Exception:
                        pass
            return True, (
                f"📡 已向局域网广播 Magic Packet 唤醒台式机！\n"
                f"• 目标网卡: Realtek PCIe GbE ({target_mac})\n"
                f"• 广播网段: {bcast_ip}:9\n"
                f"• 请确认主板 BIOS 中已开启 PME / Wake on LAN。"
            )
        except Exception as exc:
            return False, f"❌ 发送开机魔术包失败: {exc}"
