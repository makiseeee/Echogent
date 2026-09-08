"""Read-only search helpers for the Obsidian vault."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from obsidian_access import AccessMode, VaultAccessPolicy

MAX_RESULTS = 20
MAX_CONTEXT_CHARS = 240
MAX_READ_CHARS = 4_000

# 内存缓存：abs_path -> (mtime, title, text, text_casefold)
_SEARCH_CACHE: dict[str, tuple[float, str, str, str]] = {}


def clear_search_cache() -> None:
    """清理内存中的笔记搜索缓存。"""
    _SEARCH_CACHE.clear()


@dataclass(frozen=True)
class SearchResult:
    path: str
    title: str
    context: str


def _title(path: Path, text: str) -> str:
    for line in text.splitlines()[:40]:
        if line.startswith("# "):
            return line[2:].strip() or path.stem
    return path.stem


def _context(text: str, query: str) -> str:
    compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
    match = re.search(re.escape(query), compact, re.IGNORECASE)
    if not match:
        return compact[:MAX_CONTEXT_CHARS]
    start = max(0, match.start() - 80)
    return compact[start : start + MAX_CONTEXT_CHARS]


def _get_note_content(path: Path, stat_result: Any = None) -> tuple[str, str, str]:
    """获取笔记的 title, raw_text, text_casefold，优先命中 mtime 缓存。"""
    abs_key = str(path.resolve())
    mtime = stat_result.st_mtime if stat_result else path.stat().st_mtime
    cached = _SEARCH_CACHE.get(abs_key)
    if cached is not None and cached[0] == mtime:
        return cached[1], cached[2], cached[3]

    text = path.read_text(encoding="utf-8", errors="replace")
    title = _title(path, text)
    text_casefold = text.casefold()
    _SEARCH_CACHE[abs_key] = (mtime, title, text, text_casefold)
    return title, text, text_casefold


def search_vault(
    policy: VaultAccessPolicy,
    query: str,
    mode: AccessMode = AccessMode.STANDARD,
    limit: int = MAX_RESULTS,
) -> list[SearchResult]:
    """Search permitted Markdown notes by path, title, or body text."""
    query = query.strip()
    if not query:
        raise ValueError("搜索关键词不能为空")
    limit = max(1, min(int(limit), MAX_RESULTS))
    roots = ("1. Projects", "3. Resources", "5. Note")
    if mode is AccessMode.PRIVATE_ON_DEMAND:
        roots = ("2. Areas",)
    elif mode is AccessMode.ARCHIVE_ON_DEMAND:
        roots = ("4. Archives",)

    results: list[SearchResult] = []
    needle = query.casefold()
    for root_name in roots:
        try:
            root = policy.resolve_directory(root_name, mode).absolute
        except ValueError:
            continue
        for path in sorted(root.rglob("*.md")):
            try:
                allowed = policy.resolve_markdown(path, mode)
                stat_result = path.stat()
                title, text, text_casefold = _get_note_content(path, stat_result)
            except (OSError, PermissionError, ValueError):
                continue

            relative = allowed.relative.as_posix()
            if needle in relative.casefold() or needle in title.casefold() or needle in text_casefold:
                results.append(SearchResult(relative, title, _context(text, query)))
                if len(results) >= limit:
                    return results
    return results


def list_notes(
    policy: VaultAccessPolicy,
    path: str,
    mode: AccessMode = AccessMode.STANDARD,
    limit: int = MAX_RESULTS,
) -> list[str]:
    """List permitted Markdown notes below one permitted directory."""
    directory = policy.resolve_directory(path, mode)
    limit = max(1, min(int(limit), MAX_RESULTS))
    notes: list[str] = []
    for note in sorted(directory.absolute.rglob("*.md")):
        try:
            allowed = policy.resolve_markdown(note, mode)
        except (PermissionError, ValueError):
            continue
        notes.append(allowed.relative.as_posix())
        if len(notes) >= limit:
            break
    return notes


def read_note_excerpt(
    policy: VaultAccessPolicy,
    path: str,
    mode: AccessMode = AccessMode.STANDARD,
    query: str = "",
    max_chars: int = MAX_READ_CHARS,
) -> SearchResult:
    """Read only a bounded excerpt, never an unrestricted full note."""
    note = policy.resolve_markdown(path, mode)
    title, text, _ = _get_note_content(note.absolute)
    max_chars = max(200, min(int(max_chars), MAX_READ_CHARS))
    context = _context(text, query) if query.strip() else text[:max_chars]
    return SearchResult(note.relative.as_posix(), title, context[:max_chars])
