import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

class TestModelCommand(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        
        # Create mock cmd_config.json
        self.cfg_file = self.data_dir / "cmd_config.json"
        self.initial_config = {
            "admins_id": ["1249403130"],
            "provider_sources": [
                {
                    "id": "commandcode_source",
                    "provider": "openai",
                    "type": "openai_chat_completion",
                    "key": ["test_user_key"],
                    "api_base": "https://echo.1249403130.workers.dev/v1"
                }
            ],
            "provider": [
                {
                    "id": "commandcode_deepseek_v4_flash",
                    "model": "deepseek/deepseek-v4-flash",
                    "provider_source_id": "commandcode_source",
                    "enable": True
                }
            ]
        }
        self.cfg_file.write_text(json.dumps(self.initial_config, ensure_ascii=False, indent=2), encoding="utf-8")

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    @patch.dict("os.environ", {"ECHO_ASTRBOT_DATA": ""})
    async def test_model_command_menu_and_switch(self):
        import sys
        plugin_path = Path("/home/wenbo/aaage/astrbot/data/plugins/echo-tools")
        if str(plugin_path) not in sys.path:
            sys.path.insert(0, str(plugin_path))
        
        from main import EchoTools

        context = MagicMock()
        mock_inst = MagicMock()
        mock_inst.set_model = MagicMock()
        context.provider_manager.inst_map = {"commandcode_deepseek_v4_flash": mock_inst}
        context.provider_manager.providers_config = [{"id": "commandcode_deepseek_v4_flash", "model": "deepseek/deepseek-v4-flash"}]

        plugin = EchoTools(context)
        plugin._data_file = lambda name: self.cfg_file

        mock_models_response = {
            "object": "list",
            "data": [
                {"id": "claude-sonnet-5"},
                {"id": "deepseek/deepseek-v4-flash"},
                {"id": "z-ai/glm-5.3-flash"},
                {"id": "Qwen/Qwen3.7-Max"}
            ]
        }

        # 1. Test listing menu
        event = MagicMock()
        event.get_sender_id.return_value = "1249403130"
        event.message_str = "/模型"
        event.plain_result = lambda text: text

        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_models_response)
            mock_get.return_value.__aenter__.return_value = mock_resp

            results = [r async for r in plugin.model_command(event)]
            self.assertEqual(len(results), 1)
            menu_text = results[0]
            self.assertIn("当前云端实时可用模型列表", menu_text)
            self.assertIn("[2] deepseek/deepseek-v4-flash (当前使用 🌟)", menu_text)
            self.assertIn("[3] z-ai/glm-5.3-flash", menu_text)

        # 2. Test switching by index: /模型 3
        event.message_str = "/模型 3"
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_models_response)
            mock_get.return_value.__aenter__.return_value = mock_resp

            results = [r async for r in plugin.model_command(event)]
            self.assertEqual(len(results), 1)
            self.assertIn("z-ai/glm-5.3-flash", results[0])
            self.assertIn("即刻生效", results[0])
            mock_inst.set_model.assert_called_with("z-ai/glm-5.3-flash")

            # Verify persisted to disk
            saved_cfg = json.loads(self.cfg_file.read_text(encoding="utf-8"))
            self.assertEqual(saved_cfg["provider"][0]["model"], "z-ai/glm-5.3-flash")

        # 3. Test switching by keyword: /模型 qwen
        event.message_str = "/模型 qwen"
        with patch("aiohttp.ClientSession.get") as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.json = AsyncMock(return_value=mock_models_response)
            mock_get.return_value.__aenter__.return_value = mock_resp

            results = [r async for r in plugin.model_command(event)]
            self.assertEqual(len(results), 1)
            self.assertIn("Qwen/Qwen3.7-Max", results[0])
            mock_inst.set_model.assert_called_with("Qwen/Qwen3.7-Max")

            saved_cfg = json.loads(self.cfg_file.read_text(encoding="utf-8"))
            self.assertEqual(saved_cfg["provider"][0]["model"], "Qwen/Qwen3.7-Max")


if __name__ == "__main__":
    unittest.main()
