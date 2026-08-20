from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
