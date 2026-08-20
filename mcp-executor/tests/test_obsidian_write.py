from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_access import VaultAccessPolicy
from obsidian_write import NoteWriteService


class NoteWriteServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        for name in ("1. Projects", "2. Areas", "3. Resources", "5. Note"):
            (self.root / name).mkdir()
        (self.root / "3. Resources/old.md").write_text("# Old\n", encoding="utf-8")
        self.service = NoteWriteService(VaultAccessPolicy(self.root))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prepare_does_not_write_and_commit_creates_linked_note(self):
        operation = self.service.prepare(
            "owner",
            "1. Projects/new.md",
            "New",
            "Body",
            ["3. Resources/old.md"],
            {"tags": ["project"]},
        )
        target = self.root / operation.path
        self.assertFalse(target.exists())
        self.service.commit("owner", operation.operation_id)
        text = target.read_text(encoding="utf-8")
        self.assertIn("[[3. Resources/old]]", text)
        self.assertIn('tags: ["project"]', text)

    def test_overwrite_private_and_wrong_owner_are_denied(self):
        with self.assertRaises(FileExistsError):
            self.service.prepare("owner", "3. Resources/old.md", "Old", "Body")
        with self.assertRaises(PermissionError):
            self.service.prepare("owner", "2. Areas/private.md", "Private", "Body")
        with self.assertRaises(PermissionError):
            self.service.prepare("owner", "3. Resources/passwords.md", "Private", "Body")
        operation = self.service.prepare("owner", "5. Note/new.md", "New", "Body")
        with self.assertRaises(PermissionError):
            self.service.commit("other", operation.operation_id)

    def test_cancel_removes_pending_operation(self):
        operation = self.service.prepare("owner", "5. Note/cancel.md", "Cancel", "Body")
        self.service.cancel("owner", operation.operation_id)
        with self.assertRaises(ValueError):
            self.service.commit("owner", operation.operation_id)

    def test_prepare_link_uses_relevant_heading_and_commit_writes_backup(self):
        old = self.root / "3. Resources/old.md"
        old.write_text("# Old\n\n## 模型\n\n正文\n\n## 其他\n\n末尾\n", encoding="utf-8")
        new = self.root / "3. Resources/new.md"
        new.write_text("# New\n", encoding="utf-8")
        operation = self.service.prepare_link("owner", "3. Resources/old.md", "3. Resources/new.md", "模型")
        self.assertEqual(operation.heading, "## 模型")
        self.assertNotIn("[[3. Resources/new]]", old.read_text(encoding="utf-8"))
        self.service.commit_link("owner", operation.operation_id)
        text = old.read_text(encoding="utf-8")
        self.assertLess(text.index("[[3. Resources/new]]"), text.index("## 其他"))

    def test_link_commit_rejects_concurrent_edit(self):
        new = self.root / "3. Resources/new.md"
        new.write_text("# New\n", encoding="utf-8")
        operation = self.service.prepare_link("owner", "3. Resources/old.md", "3. Resources/new.md")
        (self.root / "3. Resources/old.md").write_text("changed", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            self.service.commit_link("owner", operation.operation_id)


if __name__ == "__main__":
    unittest.main()
