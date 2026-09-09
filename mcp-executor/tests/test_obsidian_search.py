from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_ECHO_TOOLS_DIR = Path(__file__).resolve().parents[2] / "astrbot" / "data" / "plugins" / "echo-tools"
_ECHO_OBSIDIAN_DIR = _ECHO_TOOLS_DIR / "obsidian"
if str(_ECHO_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_TOOLS_DIR))
if str(_ECHO_OBSIDIAN_DIR) not in sys.path:
    sys.path.insert(0, str(_ECHO_OBSIDIAN_DIR))

from obsidian_access import AccessMode, VaultAccessPolicy
from obsidian_search import list_notes, read_note_excerpt, search_vault


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        for name in ("1. Projects", "2. Areas", "4. Archives", "5. Note"):
            (root / name).mkdir()
        (root / "1. Projects/project.md").write_text("# Alpha\nPython sandbox notes", encoding="utf-8")
        (root / "5. Note/course.md").write_text("# Course\nAstrbot embedding", encoding="utf-8")
        (root / "2. Areas/diary.md").write_text("# Diary\nprivate keyword", encoding="utf-8")
        (root / "4. Archives/old.md").write_text("# Old\narchived keyword", encoding="utf-8")
        self.policy = VaultAccessPolicy(root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_standard_search_excludes_private_and_archive(self):
        found = search_vault(self.policy, "keyword")
        self.assertEqual(found, [])

    def test_private_and_archive_require_modes(self):
        self.assertEqual(search_vault(self.policy, "private", AccessMode.PRIVATE_ON_DEMAND)[0].path, "2. Areas/diary.md")
        self.assertEqual(search_vault(self.policy, "archived", AccessMode.ARCHIVE_ON_DEMAND)[0].path, "4. Archives/old.md")

    def test_title_and_context_and_limit(self):
        found = search_vault(self.policy, "alpha", limit=1)
        self.assertEqual(found[0].title, "Alpha")
        self.assertIn("Python", found[0].context)

    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError):
            search_vault(self.policy, " ")

    def test_list_and_bounded_read(self):
        self.assertEqual(list_notes(self.policy, "1. Projects"), ["1. Projects/project.md"])
        result = read_note_excerpt(self.policy, "1. Projects/project.md", query="sandbox")
        self.assertEqual(result.title, "Alpha")
        self.assertIn("sandbox", result.context)

    def test_fts5_chinese_and_short_queries(self):
        # Ingest Chinese notes with varying term lengths
        (self.policy.root / "1. Projects/ai_project.md").write_text("# 人工智能助手\n利用 Snapdragon 835 芯片进行终端低功耗部署。", encoding="utf-8")
        (self.policy.root / "5. Note/exam.md").write_text("# 考研复习计划\n每天坚持单词打卡与数学真题演练。", encoding="utf-8")

        # 3+ char Chinese match
        found = search_vault(self.policy, "人工智能")
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0].title, "人工智能助手")

        # 2-char Chinese short match
        found = search_vault(self.policy, "打卡")
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0].title, "考研复习计划")

        # 1-char Chinese short match
        found = search_vault(self.policy, "考")
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0].title, "考研复习计划")

        # English multi-term match
        found = search_vault(self.policy, "Snapdragon 835")
        self.assertTrue(len(found) >= 1)
        self.assertIn("芯片", found[0].context)

    def test_fts5_write_through_hook(self):
        from obsidian_search import index_single_note
        # Simulate NoteWriteService committing note to disk and immediately updating index
        instant_file = self.policy.root / "1. Projects/instant.md"
        content = "通过 Write-Through 挂钩实现的毫秒级入库索引。"
        instant_file.write_text(content, encoding="utf-8")
        index_single_note(self.policy, "1. Projects/instant.md", "即时笔记", content)

        found = search_vault(self.policy, "毫秒级")
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0].path, "1. Projects/instant.md")
        self.assertEqual(found[0].title, "即时笔记")

    def test_fts5_deleted_note_cleanup(self):
        test_file = self.policy.root / "1. Projects/to_delete.md"
        test_file.write_text("# 待删除笔记\n临时内容将在稍后被移除。", encoding="utf-8")
        # Ensure it is indexed
        from obsidian_search import clear_search_cache
        clear_search_cache()
        found = search_vault(self.policy, "临时内容")
        self.assertEqual(len(found), 1)

        # Delete from disk
        test_file.unlink()
        clear_search_cache()
        found = search_vault(self.policy, "临时内容")
        self.assertEqual(len(found), 0)


if __name__ == "__main__":
    unittest.main()
