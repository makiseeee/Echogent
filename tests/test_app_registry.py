import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

# Add echo_pc_agent to sys.path
pc_agent_path = Path(__file__).resolve().parent.parent / "echo_pc_agent"
if str(pc_agent_path) not in sys.path:
    sys.path.insert(0, str(pc_agent_path))

from modules.app_registry import AppRegistry
from modules.activity import ActivityTracker


class TestAppRegistry(unittest.TestCase):
    def setUp(self):
        # Create temp dir for isolated test database
        self.test_dir = tempfile.mkdtemp()
        # Copy real software_taxonomy.json to test dir
        real_json = pc_agent_path / "data" / "software_taxonomy.json"
        if real_json.exists():
            shutil.copy(real_json, os.path.join(self.test_dir, "software_taxonomy.json"))

        self.registry = AppRegistry(data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_default_preset_loading(self):
        apps = self.registry.list_apps()
        self.assertGreater(len(apps), 50, "Should load at least 50 apps from default presets")

        # Verify CS2
        cs2 = self.registry.get("cs2.exe")
        self.assertIsNotNone(cs2)
        self.assertEqual(cs2["category"], "gaming")
        self.assertEqual(cs2["subcategory"], "competitive_fps_moba")
        self.assertTrue(cs2["dnd_inhibit"], "CS2 must have dnd_inhibit=True")
        self.assertTrue(cs2["visual_safe"])

        # Verify WeChat
        wechat = self.registry.get("wechat.exe")
        self.assertIsNotNone(wechat)
        self.assertEqual(wechat["category"], "communication_meeting")
        self.assertFalse(wechat["visual_safe"], "WeChat must have visual_safe=False")

        # Verify Keil UV4
        uv4 = self.registry.get("uv4.exe")
        self.assertIsNotNone(uv4)
        self.assertEqual(uv4["category"], "hardware_embedded")
        self.assertEqual(uv4["subcategory"], "mcu_embedded")

    def test_sqlite_override_and_persistence(self):
        # CS2 visual_safe is initially True
        cs2_init = self.registry.get("cs2.exe")
        self.assertTrue(cs2_init["visual_safe"])

        # Update CS2 visual_safe to False
        ok = self.registry.update_app("cs2.exe", {
            "visual_safe": False,
            "custom_summary": "天梯竞技上分中",
        })
        self.assertTrue(ok)

        # In-memory cache must immediately reflect the update
        cs2_mem = self.registry.get("cs2.exe")
        self.assertFalse(cs2_mem["visual_safe"])
        self.assertEqual(cs2_mem["custom_summary"], "天梯竞技上分中")
        self.assertTrue(cs2_mem["is_user_defined"])

        # Create fresh registry instance from same test_dir to verify SQLite persistence
        new_registry = AppRegistry(data_dir=self.test_dir)
        cs2_db = new_registry.get("cs2.exe")
        self.assertFalse(cs2_db["visual_safe"], "SQLite override must persist after reload")
        self.assertEqual(cs2_db["custom_summary"], "天梯竞技上分中")
        self.assertTrue(cs2_db["is_user_defined"])

    def test_filter_by_category(self):
        coding_apps = self.registry.list_apps(category="coding")
        self.assertGreater(len(coding_apps), 0)
        for app in coding_apps:
            self.assertEqual(app["category"], "coding")

    def test_register_unseen(self):
        # Register completely unseen process
        self.registry.register_unseen("custom_gadget.exe", "My Custom Gadget")
        gadget = self.registry.get("custom_gadget.exe")
        self.assertIsNotNone(gadget)
        self.assertEqual(gadget["category"], "other")
        self.assertEqual(gadget["subcategory"], "unseen")
        self.assertEqual(gadget["app_name"], "My Custom Gadget")


class TestActivityTrackerIntegration(unittest.TestCase):
    def setUp(self):
        self.tracker = ActivityTracker()

    def test_classify_known_apps(self):
        # 1. CS2
        res_cs2 = self.tracker.classify("cs2.exe", "Counter-Strike 2", 10)
        self.assertEqual(res_cs2["category"], "gaming")
        self.assertTrue(res_cs2["dnd_inhibit"])
        self.assertTrue(res_cs2["visual_safe"])

        # 2. Tencent Meeting
        res_meeting = self.tracker.classify("wemeetapp.exe", "腾讯会议", 5)
        self.assertEqual(res_meeting["category"], "communication_meeting")
        self.assertTrue(res_meeting["dnd_inhibit"])
        self.assertFalse(res_meeting["visual_safe"])

        # 3. Keil UV4
        res_uv4 = self.tracker.classify("uv4.exe", "Project1 - Keil uVision5", 3)
        self.assertEqual(res_uv4["category"], "hardware_embedded")
        self.assertFalse(res_uv4["dnd_inhibit"])
        self.assertTrue(res_uv4["visual_safe"])

        # 4. MATLAB
        res_matlab = self.tracker.classify("matlab.exe", "MATLAB R2024a", 2)
        self.assertEqual(res_matlab["category"], "research_simulation")

    def test_classify_browser_dynamic(self):
        res = self.tracker.classify("chrome.exe", "arXiv:2401.12345v1 [cs.AI] - Google Chrome", 12)
        self.assertEqual(res["category"], "research_simulation")
        self.assertEqual(res["subcategory"], "paper_reading")

        res_bili = self.tracker.classify("chrome.exe", "哔哩哔哩 (゜-゜)つロ 干杯~ - bilibili", 20)
        self.assertEqual(res_bili["category"], "video_leisure")
        self.assertFalse(res_bili["visual_safe"])


if __name__ == "__main__":
    unittest.main()
