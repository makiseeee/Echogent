"""DeskGlanceService 多模态桌边偷瞄服务单元测试。"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "astrbot" / "data" / "plugins" / "echo-tools"
sys.path.insert(0, str(PLUGIN_ROOT))

from services.desk_glance import DeskGlanceService


class TestDeskGlance(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "cmd_config.json")
        sample_config = {
            "provider_sources": [
                {
                    "id": "zhipu_source",
                    "api_base": "https://open.bigmodel.cn/api/paas/v4",
                    "key": ["test_zhipu_secret_key_12345"],
                }
            ]
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(sample_config, f)

        self.service = DeskGlanceService(config_path=self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_zhipu_key(self):
        key = self.service._get_zhipu_key()
        self.assertEqual(key, "test_zhipu_secret_key_12345")

    def test_transient_photo_cleanup(self):
        test_img_path = os.path.join(self.temp_dir.name, "tmp_test_snap.jpg")
        with open(test_img_path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0test_jpeg_bytes\xff\xd9")

        # Mock subprocess.run
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, b64_data = self.service.take_transient_photo(output_path=test_img_path)
            self.assertTrue(ok)
            self.assertTrue(len(b64_data) > 0)
            # 验证原始图片文件已被物理销毁
            self.assertFalse(os.path.exists(test_img_path))

    async def test_glance_privacy_mode(self):
        reply = await self.service.glance_desk(
            pc_activity={"privacy_mode": True, "app": "InPrivate Browser"},
            reason="test",
        )
        self.assertIn("隐私模式", reply)

    async def test_glance_cooldown(self):
        self.service.last_glance_ts = time.time()
        reply = await self.service.glance_desk(pc_activity={}, reason="test")
        self.assertIn("刚瞄过你呢", reply)

    async def test_fallback_without_camera(self):
        reply = self.service._fallback_reply_without_camera(
            {"status": "online", "app": "PyCharm", "summary": "编写代码"}
        )
        self.assertIn("PyCharm", reply)

    async def test_mock_vlm_glance_success(self):
        # Reset cooldown
        self.service.last_glance_ts = 0.0

        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "戴着耳机托着腮看视频呢，下巴都快压酸啦~"
                        }
                    }
                ]
            }
        )

        mock_session = MagicMock()
        mock_session.post.return_value.__aenter__.return_value = mock_resp

        with patch.object(self.service, "take_transient_photo", return_value=(True, "fake_base64_data")):
            with patch("core.http_client.HttpClient.get_session", new_callable=AsyncMock) as mock_get_sess:
                mock_get_sess.return_value = mock_session
                reply = await self.service.glance_desk(
                    pc_activity={
                        "status": "online",
                        "app": "哔哩哔哩",
                        "category": "video",
                        "duration_minutes": 15,
                    },
                    reason="user_inquiry",
                )
                self.assertIn("戴着耳机托着腮", reply)


if __name__ == "__main__":
    unittest.main()
