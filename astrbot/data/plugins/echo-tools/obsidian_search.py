"""Read-only search helpers for the Obsidian vault."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from obsidian_access import AccessMode, VaultAccessPolicy

MAX_RESULTS = 20
MAX_CONTEXT_CHARS = 240
MAX_READ_CHARS = 4_000


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
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError, ValueError):
                continue
            title = _title(path, text)
            relative = allowed.relative.as_posix()
            haystack = f"{relative}\n{title}\n{text}".casefold()
            if needle in haystack:
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
    """Read a bounded note or excerpt up to max_chars, preserving structure and Markdown formatting."""
    note = policy.resolve_markdown(path, mode)
    text = note.absolute.read_text(encoding="utf-8", errors="replace")
    max_chars = max(200, min(int(max_chars), MAX_READ_CHARS))

    # Notes that fit within max_chars are returned completely intact with formatting
    if len(text) <= max_chars:
        return SearchResult(note.relative.as_posix(), _title(note.absolute, text), text)

    # For large notes, extract a relevant window around query if provided
    query = query.strip()
    if query:
        match = re.search(re.escape(query), text, re.IGNORECASE)
        if not match:
            # Try searching for individual words (2+ chars)
            words = [w for w in re.split(r"\s+", query) if len(w) >= 2]
            for word in words:
                match = re.search(re.escape(word), text, re.IGNORECASE)
                if match:
                    break

        if match:
            half = max_chars // 2
            start = max(0, match.start() - half)
            end = min(len(text), start + max_chars)
            if end - start < max_chars:
                start = max(0, end - max_chars)
            excerpt = text[start:end]
            return SearchResult(note.relative.as_posix(), _title(note.absolute, text), excerpt)

    return SearchResult(note.relative.as_posix(), _title(note.absolute, text), text[:max_chars])
