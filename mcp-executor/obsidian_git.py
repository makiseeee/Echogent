"""Best-effort Git synchronization for a shared Obsidian vault."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import base64
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from typing import Callable, TypeVar


LOG = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(frozen=True)
class GitSyncResult:
    success: bool
    changed: bool = False
    committed: bool = False
    pushed: bool = False
    pull_warning: str = ""
    push_warning: str = ""
    error: str = ""

    def __bool__(self) -> bool:
        return self.success


class VaultGitSync:
    """Serialize pull/write/commit/push operations without blocking offline writes."""

    def __init__(
        self,
        vault: Path | str,
        remote: str = "origin",
        branch: str = "main",
        timeout_seconds: int = 30,
        username: str = "",
        token: str = "",
    ):
        self.vault = Path(vault).resolve()
        self.remote = remote
        self.branch = branch
        self.timeout_seconds = max(5, int(timeout_seconds))
        self.username = username
        self.token = token
        self._lock = threading.Lock()
        self._last_pull_time: float = 0.0
        self._pull_cache_ttl: float = 60.0

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if self.username and self.token:
            credential = base64.b64encode(f"{self.username}:{self.token}".encode()).decode()
            env.update({
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "http.extraHeader",
                "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credential}",
                "GIT_TERMINAL_PROMPT": "0",
            })
        return subprocess.run(
            ["git", "-C", str(self.vault), *args],
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=check,
            env=env,
        )

    @staticmethod
    def _message(exc: BaseException) -> str:
        if isinstance(exc, subprocess.CalledProcessError):
            return (exc.stderr or exc.stdout or str(exc)).strip()
        return str(exc).strip()

    def _abort_rebase(self) -> None:
        marker = self.vault / ".git"
        if (marker / "rebase-merge").exists() or (marker / "rebase-apply").exists():
            self._git("rebase", "--abort", check=False)

    def _pull_unlocked(self, force: bool = False) -> tuple[bool, str]:
        now = time.time()
        if not force and (now - self._last_pull_time < self._pull_cache_ttl):
            return True, ""
        try:
            self._git("pull", "--rebase", self.remote, self.branch)
            self._last_pull_time = time.time()
            return True, ""
        except (subprocess.SubprocessError, OSError) as exc:
            self._abort_rebase()
            warning = self._message(exc)
            LOG.warning("Obsidian git pull failed; continuing offline: %s", warning)
            return False, warning

    def pull_if_stale(self, max_age_sec: float = 30.0) -> GitSyncResult:
        """若距离上次 pull 超过 max_age_sec 秒则执行拉取，否则复用避免频繁网络等待。"""
        with self._lock:
            now = time.time()
            if (now - self._last_pull_time) < max_age_sec:
                return GitSyncResult(success=True, pull_warning="")
            ok, warning = self._pull_unlocked(force=True)
            return GitSyncResult(success=ok, pull_warning=warning, error="" if ok else warning)

    def pull_latest(self, force: bool = True) -> GitSyncResult:
        if not force:
            return self.pull_if_stale(self._pull_cache_ttl)
        with self._lock:
            ok, warning = self._pull_unlocked(force=True)
            return GitSyncResult(success=ok, pull_warning=warning, error="" if ok else warning)

    def atomic_write(self, action_func: Callable[[], T], commit_message: str) -> tuple[T, GitSyncResult]:
        with self._lock:
            _, pull_warning = self._pull_unlocked()
            try:
                value = action_func()
            except Exception:
                LOG.exception("Obsidian write action failed")
                raise

            try:
                changed = bool(self._git("status", "--porcelain").stdout.strip())
                if not changed:
                    return value, GitSyncResult(success=True, pull_warning=pull_warning)
                self._git("add", "--all")
                stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")
                self._git("commit", "-m", f"agent: {commit_message} ({stamp})")
            except (subprocess.SubprocessError, OSError) as exc:
                error = self._message(exc)
                LOG.error("Obsidian local git commit failed: %s", error)
                return value, GitSyncResult(
                    success=False, changed=True, pull_warning=pull_warning, error=error
                )

            try:
                self._git("push", self.remote, self.branch)
                return value, GitSyncResult(
                    success=True, changed=True, committed=True, pushed=True,
                    pull_warning=pull_warning,
                )
            except (subprocess.SubprocessError, OSError) as exc:
                warning = self._message(exc)
                # A concurrent writer may have advanced the remote after our pull.
                if "non-fast-forward" in warning.lower() or "rejected" in warning.lower():
                    ok, retry_warning = self._pull_unlocked()
                    if ok:
                        try:
                            self._git("push", self.remote, self.branch)
                            return value, GitSyncResult(
                                success=True, changed=True, committed=True, pushed=True,
                                pull_warning=pull_warning,
                            )
                        except (subprocess.SubprocessError, OSError) as retry_exc:
                            warning = self._message(retry_exc)
                    elif retry_warning:
                        warning = f"{warning}; rebase retry: {retry_warning}"
                LOG.warning("Obsidian git push failed; commit kept locally: %s", warning)
                return value, GitSyncResult(
                    success=True, changed=True, committed=True, pushed=False,
                    pull_warning=pull_warning, push_warning=warning,
                )

    def atomic_transaction(self, action_func: Callable[[], T], commit_message: str) -> tuple[T, GitSyncResult]:
        """Alias documenting that action_func may modify multiple files atomically."""
        return self.atomic_write(action_func, commit_message)

    def modify_file(
        self,
        relative_path: str,
        transform_func: Callable[[str], str],
        commit_message: str,
    ) -> GitSyncResult:
        target = (self.vault / relative_path).resolve()
        if not target.is_relative_to(self.vault):
            raise PermissionError("目标路径不在 Obsidian 仓库内")

        def action() -> None:
            old_text = target.read_text(encoding="utf-8")
            new_text = transform_func(old_text)
            if not isinstance(new_text, str):
                raise TypeError("transform_func 必须返回字符串")
            if new_text != old_text:
                target.write_text(new_text, encoding="utf-8")

        _, result = self.atomic_write(action, commit_message)
        return result
