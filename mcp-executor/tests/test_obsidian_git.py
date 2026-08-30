from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from obsidian_git import VaultGitSync


def git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, text=True, capture_output=True
    ).stdout.strip()


class VaultGitSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.remote = root / "remote.git"
        self.vault = root / "vault"
        subprocess.run(["git", "init", "--bare", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "init", "-b", "main", str(self.vault)], check=True, capture_output=True)
        git(self.vault, "config", "user.name", "Echo Test")
        git(self.vault, "config", "user.email", "echo-test@localhost")
        git(self.vault, "remote", "add", "origin", str(self.remote))
        (self.vault / "note.md").write_text("old\n", encoding="utf-8")
        git(self.vault, "add", ".")
        git(self.vault, "commit", "-m", "initial")
        git(self.vault, "push", "-u", "origin", "main")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_modify_commits_and_pushes(self):
        sync = VaultGitSync(self.vault)
        result = sync.modify_file("note.md", lambda old: old + "new\n", "update note")
        self.assertTrue(result)
        self.assertTrue(result.committed)
        self.assertTrue(result.pushed)
        self.assertIn("new", (self.vault / "note.md").read_text())

    def test_offline_remote_keeps_local_commit(self):
        git(self.vault, "remote", "set-url", "origin", str(self.vault / "missing.git"))
        sync = VaultGitSync(self.vault, timeout_seconds=5)
        result = sync.modify_file("note.md", lambda old: old + "offline\n", "offline update")
        self.assertTrue(result)
        self.assertTrue(result.committed)
        self.assertFalse(result.pushed)
        self.assertTrue(result.pull_warning)
        self.assertTrue(result.push_warning)
        self.assertEqual(git(self.vault, "status", "--porcelain"), "")

    def test_failed_rebase_is_aborted(self):
        other = Path(self.temp_dir.name) / "other"
        subprocess.run(["git", "clone", "--branch", "main", str(self.remote), str(other)], check=True, capture_output=True)
        git(other, "config", "user.name", "Other")
        git(other, "config", "user.email", "other@localhost")
        (other / "note.md").write_text("remote\n", encoding="utf-8")
        git(other, "add", "note.md")
        git(other, "commit", "-m", "remote")
        git(other, "push", "origin", "main")
        (self.vault / "note.md").write_text("local\n", encoding="utf-8")
        git(self.vault, "commit", "-am", "local")

        result = VaultGitSync(self.vault).pull_latest()

        self.assertFalse(result)
        self.assertFalse((self.vault / ".git/rebase-merge").exists())
        self.assertFalse((self.vault / ".git/rebase-apply").exists())


if __name__ == "__main__":
    unittest.main()
