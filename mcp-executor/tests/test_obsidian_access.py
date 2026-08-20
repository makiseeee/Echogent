from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from obsidian_access import AccessMode, VaultAccessPolicy


class VaultAccessPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        for directory in (
            "1. Projects",
            "2. Areas/日记",
            "3. Resources/_attachments",
            "4. Archives",
            "5. Note",
            ".obsidian",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / "1. Projects/normal.md").write_text("project", encoding="utf-8")
        (self.root / "2. Areas/日记/2026-08-17.md").write_text("diary", encoding="utf-8")
        (self.root / "3. Resources/_password.md").write_text("denied", encoding="utf-8")
        (self.root / "3. Resources/_attachments/image.md").write_text("denied", encoding="utf-8")
        (self.root / "4. Archives/history.md").write_text("archive", encoding="utf-8")
        (self.root / "5. Note/raw.bin").write_bytes(b"data")
        (self.root / ".obsidian/config.md").write_text("denied", encoding="utf-8")
        self.policy = VaultAccessPolicy(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_standard_note_is_allowed(self):
        result = self.policy.resolve_markdown("1. Projects/normal.md")
        self.assertEqual(result.relative.as_posix(), "1. Projects/normal.md")

    def test_diary_requires_private_on_demand_mode(self):
        with self.assertRaisesRegex(PermissionError, "私聊按需"):
            self.policy.resolve_markdown("2. Areas/日记/2026-08-17.md")
        result = self.policy.resolve_markdown(
            "2. Areas/日记/2026-08-17.md",
            AccessMode.PRIVATE_ON_DEMAND,
        )
        self.assertEqual(result.mode, AccessMode.PRIVATE_ON_DEMAND)

    def test_archive_requires_archive_mode(self):
        with self.assertRaisesRegex(PermissionError, "归档"):
            self.policy.resolve_markdown("4. Archives/history.md")
        self.policy.resolve_markdown("4. Archives/history.md", AccessMode.ARCHIVE_ON_DEMAND)

    def test_sensitive_filename_is_always_denied(self):
        with self.assertRaisesRegex(PermissionError, "敏感信息"):
            self.policy.resolve_markdown("3. Resources/_password.md")

    def test_attachment_and_hidden_directories_are_denied(self):
        with self.assertRaisesRegex(PermissionError, "永久排除"):
            self.policy.resolve_markdown("3. Resources/_attachments/image.md")
        with self.assertRaisesRegex(PermissionError, "永久排除"):
            self.policy.resolve_markdown(".obsidian/config.md")

    def test_non_markdown_and_escape_are_denied(self):
        with self.assertRaisesRegex(PermissionError, "Markdown"):
            self.policy.resolve_markdown("5. Note/raw.bin")
        outside = self.root.parent / "outside.md"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        with self.assertRaisesRegex(PermissionError, "越出"):
            self.policy.resolve_markdown(outside)

    def test_symlink_escape_is_denied(self):
        outside = self.root.parent / "outside-link-target.md"
        outside.write_text("outside", encoding="utf-8")
        self.addCleanup(outside.unlink, missing_ok=True)
        link = self.root / "1. Projects/link.md"
        try:
            link.symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(PermissionError, "越出"):
            self.policy.resolve_markdown(link)


if __name__ == "__main__":
    unittest.main()
