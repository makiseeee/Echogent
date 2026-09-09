from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
import subprocess

_ECHO_TOOLS_DIR = Path(__file__).resolve().parents[2] / "astrbot" / "data" / "plugins" / "echo-tools"
_ECHO_OBSIDIAN_DIR = _ECHO_TOOLS_DIR / "obsidian"
if str(_ECHO_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_TOOLS_DIR))
if str(_ECHO_OBSIDIAN_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_OBSIDIAN_DIR))

from daily_task_manager import DailyTaskManager, TaskAmbiguityError
from obsidian_git import VaultGitSync


TEMPLATE = """---
date: {{date:YYYY-MM-DD}}
---
<!-- echo-daily:date={{date:YYYY-MM-DD}};dispatched=false;recapped=false -->
## Tasks
<!-- echo-tasks:start -->
<!-- echo-tasks:end -->
## Thino
<!-- echo-thino:start -->
<!-- echo-thino:end -->
## Journal
## Ideas
## Reflection
<!-- echo-reflection:start -->
<!-- echo-reflection:end -->
"""


class DailyTaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", "-b", "main", str(self.vault)], check=True)
        subprocess.run(["git", "-C", str(self.vault), "config", "user.name", "Test"], check=True)
        subprocess.run(["git", "-C", str(self.vault), "config", "user.email", "test@example.com"], check=True)
        (self.vault / "Templates").mkdir()
        (self.vault / "Templates/日记模板.md").write_text(TEMPLATE, encoding="utf-8")
        subprocess.run(["git", "-C", str(self.vault), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.vault), "commit", "-q", "-m", "init"], check=True)
        self.git = VaultGitSync(self.vault, timeout_seconds=5)
        self.manager = DailyTaskManager(self.git)

    def tearDown(self):
        self.temp.cleanup()

    def test_full_day_flow_and_idempotency(self):
        overdue = self.manager.ingest_task("过期任务", "2026-08-25")
        self.manager.ingest_task("普通任务", "2026-09-05")
        recurring = self.manager.ingest_task("每天喝水", is_recurring=True, cycle_rule="每天")
        first = self.manager.morning_dispatch("2026-08-26", max_tasks=1)
        self.assertEqual([item["id"] for item in first["one_time"]], [overdue["task_id"]])
        self.assertEqual([item["id"] for item in first["recurring"]], [recurring["task_id"]])
        self.assertTrue(self.manager.morning_dispatch("2026-08-26")["already_dispatched"])
        self.assertTrue(self.manager.toggle_daily_task("过期" , date_str="2026-08-26"))
        self.manager.append_thino("午饭", "2026-08-26")
        recap = self.manager.evening_recap_and_requeue("2026-08-26", "今天完成了关键任务")
        self.assertEqual(recap["completed"], 1)
        daily = (self.vault / "2. Areas/日记/2026-08-26.md").read_text(encoding="utf-8")
        self.assertIn("午饭", daily)
        self.assertIn("今天完成了关键任务", daily)

    def test_ambiguity_is_explicit(self):
        self.manager.ingest_task("写报告甲", "2026-08-26")
        self.manager.ingest_task("写报告乙", "2026-08-26")
        self.manager.morning_dispatch("2026-08-26", max_tasks=3)
        with self.assertRaises(TaskAmbiguityError):
            self.manager.toggle_daily_task("写报告", date_str="2026-08-26")

    def test_unfinished_one_time_requeues_but_recurring_does_not(self):
        res = self.manager.ingest_task("未完成任务", "2026-08-30")
        task_id = res["task_id"]
        self.manager.ingest_task("每日习惯", is_recurring=True, cycle_rule="每天")
        self.manager.morning_dispatch("2026-08-26", max_tasks=3)
        recap = self.manager.evening_recap_and_requeue("2026-08-26")
        self.assertEqual(recap["requeued"], 1)
        tasks = (self.vault / "2. Areas/日程与作息/Tasks.md").read_text(encoding="utf-8")
        self.assertIn(task_id, tasks)
        self.assertEqual(tasks.count("每日习惯"), 1)

    def test_inventory_and_partial_progress(self):
        self.manager.ingest_task("阅读论文", "2026-08-30")
        inventory = self.manager.list_inventory()
        self.assertEqual(inventory["one_time"][0]["name"], "阅读论文")
        self.assertNotIn("remarks", inventory["one_time"][0])
        self.assertNotIn("rule", inventory["one_time"][0])
        self.assertIn("completed", inventory["one_time"][0])
        self.manager.morning_dispatch("2026-08-26", max_tasks=3)
        self.manager.evening_recap_and_requeue(
            "2026-08-26", progress_notes={"阅读论文": "读完第一节"}
        )
        tasks = (self.vault / "2. Areas/日程与作息/Tasks.md").read_text(encoding="utf-8")
        self.assertIn("当前进度: 读完第一节", tasks)
