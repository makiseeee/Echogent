from __future__ import annotations

import importlib.util
import json
import unittest
from datetime import datetime
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "astrbot/data/plugins/astrbot_plugin_self_evolution/engine/nightly_batch.py"
)
SPEC = importlib.util.spec_from_file_location("nightly_batch", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)
NightlyBatchProcessor = MODULE.NightlyBatchProcessor


class FakeResponse:
    def __init__(self, payload: dict):
        self.completion_text = json.dumps(payload, ensure_ascii=False)


class FakeProvider:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    async def text_chat(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse(self.payload)


class FakeContext:
    def __init__(self, provider):
        self.provider = provider

    def get_using_provider(self, umo=None):
        return self.provider


class FakeDao:
    async def list_known_scopes(self):
        return ["private_123"]


class FakeStore:
    def __init__(self):
        self.saved = []

    async def save_daily_summary(self, scope_id, memory, summary_date):
        self.saved.append((scope_id, json.loads(memory), summary_date))
        return f"总结已保存: {summary_date}"


class FakeSummarizer:
    def __init__(self):
        self.store = FakeStore()


class FakeDailyBatch:
    def __init__(self):
        self.saved = []

    async def _fetch_scope_messages(self, scope_id, reference_dt=None):
        return (
            [
                {
                    "time": 1767225600,
                    "sender": {"user_id": "123", "nickname": "wenbo"},
                    "message": [{"type": "text", "data": {"text": "今天把任务做完了"}}],
                }
            ],
            "2026-01-01",
        )

    async def save_group_daily_report(self, scope_id, report, summary_date=None):
        self.saved.append((scope_id, report, summary_date))
        return True


class FakeProfile:
    def __init__(self):
        self.saved = []

    async def load_profile(self, scope_id, user_id):
        return "喜欢具体回应"

    async def save_profile(self, scope_id, user_id, content, nickname=""):
        self.saved.append((scope_id, user_id, content, nickname))


class FakeConfig:
    memory_enabled = True
    reflection_enabled = True


class FakePlugin:
    def __init__(self, provider):
        self.context = FakeContext(provider)
        self.dao = FakeDao()
        self.daily_batch = FakeDailyBatch()
        self.session_memory_summarizer = FakeSummarizer()
        self.profile = FakeProfile()
        self.cfg = FakeConfig()

    def get_scope_umo(self, scope_id):
        return "echo-qq:FriendMessage:123"


class NightlyBatchProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_request_routes_all_outputs(self):
        provider = FakeProvider(
            {
                "memory": {
                    "overview": "完成了当天任务",
                    "key_facts": ["当天任务已经完成"],
                    "key_entities": ["任务"],
                    "tags": ["日常"],
                },
                "daily_report": {
                    "topic": "任务推进",
                    "emotion": "轻松",
                    "disputes": "无",
                    "active_members": ["wenbo"],
                    "notable_events": ["完成任务"],
                },
                "private_profile": "喜欢把任务做完后再休息",
            }
        )
        plugin = FakePlugin(provider)

        stats = await NightlyBatchProcessor(plugin).run(datetime(2026, 1, 2, 0, 10))

        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(stats["memory_saved"], 1)
        self.assertEqual(stats["reports_saved"], 1)
        self.assertEqual(stats["profiles_saved"], 1)
        self.assertEqual(plugin.session_memory_summarizer.store.saved[0][2], "2026-01-01")
        self.assertEqual(plugin.daily_batch.saved[0][1]["topic"], "任务推进")
        self.assertEqual(plugin.profile.saved[0][1], "123")

    async def test_invalid_json_writes_nothing(self):
        provider = FakeProvider({})
        provider.text_chat = self._invalid_response(provider)
        plugin = FakePlugin(provider)

        stats = await NightlyBatchProcessor(plugin).run(datetime(2026, 1, 2, 0, 10))

        self.assertEqual(stats["failed"], 1)
        self.assertFalse(plugin.session_memory_summarizer.store.saved)
        self.assertFalse(plugin.daily_batch.saved)
        self.assertFalse(plugin.profile.saved)

    @staticmethod
    def _invalid_response(provider):
        async def respond(**kwargs):
            provider.calls.append(kwargs)
            response = FakeResponse({})
            response.completion_text = "not json"
            return response

        return respond


if __name__ == "__main__":
    unittest.main()

