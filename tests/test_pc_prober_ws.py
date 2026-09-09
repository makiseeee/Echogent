import asyncio
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

plugin_path = Path(__file__).resolve().parent.parent / "astrbot" / "data" / "plugins" / "echo-tools"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

pc_agent_path = Path(__file__).resolve().parent.parent / "echo_pc_agent"
if str(pc_agent_path) not in sys.path:
    sys.path.insert(0, str(pc_agent_path))

import aiohttp
from core.config import PluginConfig
from core.event_bus import EventBus, PCActivityEvent
from sentries.pc_prober import PCProber
from server import encode_ws_frame, read_ws_frame, WSClient


class TestRFC6455Framing(unittest.TestCase):
    """测试原生标准库实现的 RFC 6455 握手与编解码逻辑。"""

    def test_encode_unmasked_text_frame_short(self):
        text = "hello"
        frame = encode_ws_frame(text.encode("utf-8"), opcode=0x1)
        # Opcode 1 (text) with FIN=1: 0x81
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 5)
        self.assertEqual(frame[2:], b"hello")

    def test_encode_unmasked_text_frame_medium(self):
        payload = b"x" * 200
        frame = encode_ws_frame(payload, opcode=0x1)
        self.assertEqual(frame[0], 0x81)
        self.assertEqual(frame[1], 126)
        length = struct.unpack("!H", frame[2:4])[0]
        self.assertEqual(length, 200)
        self.assertEqual(frame[4:], payload)

    def test_read_masked_text_frame(self):
        # 客户端上行必须包含掩码
        mask = b"\x12\x34\x56\x78"
        raw_data = b"ping"
        masked_data = bytes(b ^ mask[i % 4] for i, b in enumerate(raw_data))

        # Header: FIN+opcode 1 (0x81), MASK=1 + len 4 (0x84)
        mock_socket_bytes = b"\x81\x84" + mask + masked_data

        class MockSocket:
            def __init__(self, data):
                self.buf = data
                self.pos = 0

            def recv(self, size):
                chunk = self.buf[self.pos : self.pos + size]
                self.pos += len(chunk)
                return chunk

        sock = MockSocket(mock_socket_bytes)
        opcode, payload = read_ws_frame(sock)
        self.assertEqual(opcode, 0x1)
        self.assertEqual(payload, b"ping")


class TestPCProberWebSocket(unittest.IsolatedAsyncioTestCase):
    """测试 PCProber 接收 WebSocket 报文与总线驱动能力。"""

    def setUp(self):
        self.bus = EventBus()
        self.config = PluginConfig()
        self.prober = PCProber(self.config, bus=self.bus)

    async def test_apply_payload_triggers_event_bus(self):
        received_events = []
        self.bus.subscribe(PCActivityEvent, lambda ev: received_events.append(ev))

        payload = {
            "status": "online",
            "app": "Code",
            "category": "coding",
            "window_title": "pc_prober.py - aaage",
            "duration_minutes": 42,
            "idle_seconds": 15,
            "is_locked": False,
        }

        await self.prober._apply_payload(payload)

        self.assertTrue(self.prober.online)
        self.assertEqual(self.prober.detail, "Code")
        self.assertEqual(len(received_events), 1)

        ev = received_events[0]
        self.assertTrue(ev.online)
        self.assertEqual(ev.app, "Code")
        self.assertEqual(ev.category, "coding")
        self.assertEqual(ev.duration_minutes, 42)

    async def test_ws_listener_stream(self):
        received_events = []
        self.bus.subscribe(PCActivityEvent, lambda ev: received_events.append(ev))

        sample_json = json.dumps({
            "status": "online",
            "app": "Counter-Strike 2",
            "category": "gaming",
            "window_title": "Counter-Strike 2",
            "duration_minutes": 18,
            "idle_seconds": 5,
            "is_locked": False,
        })

        mock_msg = MagicMock()
        mock_msg.type = aiohttp.WSMsgType.TEXT
        mock_msg.data = sample_json

        class MockWS:
            def __init__(self):
                self.yielded = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            def __aiter__(self):
                return self

            async def __anext__(self):
                if not self.yielded:
                    self.yielded = True
                    return mock_msg
                raise StopAsyncIteration

        mock_session = AsyncMock()
        mock_session.ws_connect = MagicMock(return_value=MockWS())

        with patch("sentries.pc_prober.HttpClient.get_session", AsyncMock(return_value=mock_session)):
            await self.prober._ws_listener_loop()

        self.assertTrue(self.prober.online)
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0].app, "Counter-Strike 2")
        self.assertEqual(received_events[0].category, "gaming")

    async def test_probe_computer_http_fallback(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "status": "online",
            "app": "Chrome",
            "category": "research",
            "summary": "查阅论文",
            "duration_minutes": 10,
            "idle_seconds": 0,
        })

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm

        with patch("sentries.pc_prober.HttpClient.get_session", AsyncMock(return_value=mock_session)):
            online, detail = await self.prober.probe_computer(timeout_sec=1.0)
            self.assertTrue(online)
            self.assertIn("Chrome", detail)


if __name__ == "__main__":
    unittest.main()
