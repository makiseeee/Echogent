"""SQLite FTS5 full-text search engine and helpers for the Obsidian vault."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any

try:
    from .obsidian_access import (
        AccessMode,
        VaultAccessPolicy,
        DENIED_DIRECTORIES,
        SENSITIVE_NAME_MARKERS,
        STANDARD_ROOTS,
        PRIVATE_ROOTS,
        ARCHIVE_ROOTS,
    )
except ImportError:
    from obsidian.obsidian_access import (
        AccessMode,
        VaultAccessPolicy,
        DENIED_DIRECTORIES,
        SENSITIVE_NAME_MARKERS,
        STANDARD_ROOTS,
        PRIVATE_ROOTS,
        ARCHIVE_ROOTS,
    )

logger = logging.getLogger("echo.obsidian_search")

MAX_RESULTS = 20
MAX_CONTEXT_CHARS = 240
MAX_READ_CHARS = 4_000
INDEX_TTL_SECONDS = 30.0

# In-memory fast cache: abs_path -> (mtime, title, text, text_casefold)
_SEARCH_CACHE: dict[str, tuple[float, str, str, str]] = {}
_LAST_SYNC_TIMES: dict[str, float] = {}
_INDEX_LOCK = threading.Lock()


def clear_search_cache() -> None:
    """清理内存中的笔记搜索缓存及数据库同步时间戳。"""
    with _INDEX_LOCK:
        _SEARCH_CACHE.clear()
        _LAST_SYNC_TIMES.clear()


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


def _is_excluded(path: Path) -> bool:
    """Check if file should be excluded from search (denied dirs, hidden dirs, sensitive markers)."""
    parts = path.parts
    for p in parts:
        low = p.casefold()
        if low.startswith(".") or low in DENIED_DIRECTORIES:
            return True
    filename = parts[-1].casefold() if parts else ""
    if any(marker in filename for marker in SENSITIVE_NAME_MARKERS):
        return True
    return False


def _get_db_path(policy: VaultAccessPolicy) -> Path:
    obsidian_dir = policy.root / ".obsidian"
    obsidian_dir.mkdir(parents=True, exist_ok=True)
    return obsidian_dir / "echo_vault_index.db"


def _open_db(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path), timeout=10.0)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.execute("""
        CREATE TABLE IF NOT EXISTS note_meta (
            path TEXT PRIMARY KEY,
            mtime REAL NOT NULL,
            title TEXT NOT NULL,
            file_size INTEGER NOT NULL
        )
    """)
    con.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5(
            path,
            title,
            body,
            tokenize='trigram'
        )
    """)
    return con


def _sync_vault_index(
    policy: VaultAccessPolicy,
    db_path: Path,
    mode: AccessMode = AccessMode.STANDARD,
    force: bool = False,
) -> None:
    """Incrementally synchronize disk notes with SQLite FTS5 index based on mtime and TTL."""
    key = str(db_path.resolve())
    now = time.time()
    if not force and (now - _LAST_SYNC_TIMES.get(key, 0.0) < INDEX_TTL_SECONDS):
        return

    with _INDEX_LOCK:
        if not force and (time.time() - _LAST_SYNC_TIMES.get(key, 0.0) < INDEX_TTL_SECONDS):
            return

        all_roots = sorted(STANDARD_ROOTS | PRIVATE_ROOTS | ARCHIVE_ROOTS)
        roots_to_scan = tuple(policy.root / r for r in all_roots)

        try:
            with _open_db(db_path) as con:
                existing_meta: dict[str, float] = {
                    row[0]: row[1] for row in con.execute("SELECT path, mtime FROM note_meta")
                }

                seen_paths: set[str] = set()
                to_insert_meta: list[tuple[str, float, str, int]] = []
                to_insert_fts: list[tuple[str, str, str]] = []
                to_delete_paths: list[str] = []

                for root_dir in roots_to_scan:
                    if not root_dir.exists():
                        continue
                    for entry in root_dir.rglob("*.md"):
                        try:
                            rel = entry.relative_to(policy.root)
                            if _is_excluded(rel):
                                continue
                            rel_posix = rel.as_posix()
                            seen_paths.add(rel_posix)

                            st = entry.stat()
                            mtime = st.st_mtime
                            if rel_posix in existing_meta and abs(existing_meta[rel_posix] - mtime) < 1e-4:
                                continue

                            # File is new or changed
                            text = entry.read_text(encoding="utf-8", errors="replace")
                            title = _title(entry, text)
                            to_delete_paths.append(rel_posix)
                            to_insert_meta.append((rel_posix, mtime, title, st.st_size))
                            to_insert_fts.append((rel_posix, title, text))
                        except (OSError, PermissionError, ValueError):
                            continue

                # Find removed files
                for old_path in existing_meta:
                    if old_path not in seen_paths:
                        to_delete_paths.append(old_path)

                if to_delete_paths:
                    for p in to_delete_paths:
                        con.execute("DELETE FROM note_meta WHERE path = ?", (p,))
                        con.execute("DELETE FROM note_fts WHERE path = ?", (p,))

                if to_insert_meta:
                    con.executemany("INSERT OR REPLACE INTO note_meta VALUES (?, ?, ?, ?)", to_insert_meta)
                    con.executemany("INSERT INTO note_fts VALUES (?, ?, ?)", to_insert_fts)

                con.commit()
                _LAST_SYNC_TIMES[key] = time.time()
        except Exception as e:
            logger.warning(f"Vault FTS sync failed ({e}); search will proceed with best effort.")


def index_single_note(
    policy: VaultAccessPolicy,
    rel_path: str,
    title: str,
    body: str,
    mtime: float | None = None,
) -> None:
    """Write-through hook to immediately update FTS5 index for created/updated notes."""
    if mtime is None:
        mtime = time.time()
    db_path = _get_db_path(policy)
    with _INDEX_LOCK:
        try:
            with _open_db(db_path) as con:
                con.execute("DELETE FROM note_meta WHERE path = ?", (rel_path,))
                con.execute("DELETE FROM note_fts WHERE path = ?", (rel_path,))
                con.execute(
                    "INSERT INTO note_meta VALUES (?, ?, ?, ?)",
                    (rel_path, mtime, title, len(body.encode("utf-8"))),
                )
                con.execute("INSERT INTO note_fts VALUES (?, ?, ?)", (rel_path, title, body))
                con.commit()
        except Exception as e:
            logger.warning(f"Failed to write-through index note {rel_path}: {e}")


def _search_vault_linear(
    policy: VaultAccessPolicy,
    query: str,
    mode: AccessMode,
    limit: int,
) -> list[SearchResult]:
    """Fallback linear search in case SQLite FTS5 encounters an unrecoverable failure."""
    limit = max(1, min(int(limit), MAX_RESULTS))
    if mode == AccessMode.PRIVATE_ON_DEMAND:
        roots = ("2. Areas",)
    elif mode == AccessMode.ARCHIVE_ON_DEMAND:
        roots = ("4. Archives",)
    else:
        roots = ("1. Projects", "3. Resources", "3. Knowledge", "5. Note")

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


def search_vault(
    policy: VaultAccessPolicy,
    query: str,
    mode: AccessMode = AccessMode.STANDARD,
    limit: int = MAX_RESULTS,
) -> list[SearchResult]:
    """Search permitted Markdown notes with SQLite FTS5 trigram full-text index."""
    query = query.strip()
    if not query:
        raise ValueError("搜索关键词不能为空")
    limit = max(1, min(int(limit), MAX_RESULTS))

    # Allowed root prefixes
    if mode == AccessMode.PRIVATE_ON_DEMAND:
        allowed_prefixes = ("2. Areas/",)
    elif mode == AccessMode.ARCHIVE_ON_DEMAND:
        allowed_prefixes = ("4. Archives/",)
    else:
        allowed_prefixes = ("1. Projects/", "3. Resources/", "3. Knowledge/", "5. Note/")

def _execute_query(
    con: sqlite3.Connection,
    query: str,
    allowed_prefixes: tuple[str, ...],
    limit: int,
) -> list[SearchResult]:
    words = [w.strip() for w in query.split() if w.strip()]
    if not words:
        return []

    long_words = [w for w in words if len(w) >= 3]
    short_words = [w for w in words if len(w) < 3]

    root_sql = "(" + " OR ".join("path LIKE ?" for _ in allowed_prefixes) + ")"
    root_params = [f"{prefix}%" for prefix in allowed_prefixes]

    if long_words:
        match_terms = " ".join(f'"{w.replace(chr(34), chr(34)+chr(34))}"' for w in long_words)
        where_clauses = ["note_fts MATCH ?", root_sql]
        params: list[Any] = [match_terms] + list(root_params)

        for sw in short_words:
            where_clauses.append("(title LIKE ? OR body LIKE ? OR path LIKE ?)")
            like_val = f"%{sw}%"
            params.extend([like_val, like_val, like_val])

        sql = f"""
            SELECT path, title, body, rank
            FROM note_fts
            WHERE {' AND '.join(where_clauses)}
            ORDER BY rank
            LIMIT ?
        """
        params.append(limit)
        rows = con.execute(sql, params).fetchall()
    else:
        where_clauses = [root_sql]
        params = list(root_params)
        title_cases: list[str] = []

        for sw in short_words:
            where_clauses.append("(title LIKE ? OR body LIKE ? OR path LIKE ?)")
            like_val = f"%{sw}%"
            params.extend([like_val, like_val, like_val])
            title_cases.append(f"WHEN title LIKE '%{sw}%' THEN 0")

        order_sql = (
            f"ORDER BY (CASE {' '.join(title_cases)} ELSE 1 END), length(body) ASC"
            if title_cases
            else ""
        )
        sql = f"""
            SELECT path, title, body, 0.0 as rank
            FROM note_fts
            WHERE {' AND '.join(where_clauses)}
            {order_sql}
            LIMIT ?
        """
        params.append(limit)
        rows = con.execute(sql, params).fetchall()

    results: list[SearchResult] = []
    for path_str, title_str, body_str, _ in rows:
        results.append(
            SearchResult(
                path=path_str,
                title=title_str,
                context=_context(body_str, query),
            )
        )
    return results


def search_vault(
    policy: VaultAccessPolicy,
    query: str,
    mode: AccessMode = AccessMode.STANDARD,
    limit: int = MAX_RESULTS,
) -> list[SearchResult]:
    """Search permitted Markdown notes with SQLite FTS5 trigram full-text index."""
    query = query.strip()
    if not query:
        raise ValueError("搜索关键词不能为空")
    limit = max(1, min(int(limit), MAX_RESULTS))

    # Allowed root prefixes
    if mode == AccessMode.PRIVATE_ON_DEMAND:
        allowed_prefixes = ("2. Areas/",)
    elif mode == AccessMode.ARCHIVE_ON_DEMAND:
        allowed_prefixes = ("4. Archives/",)
    else:
        allowed_prefixes = ("1. Projects/", "3. Resources/", "3. Knowledge/", "5. Note/")

    try:
        db_path = _get_db_path(policy)
        _sync_vault_index(policy, db_path, mode)

        with _open_db(db_path) as con:
            results = _execute_query(con, query, allowed_prefixes, limit)
            if not results:
                # 0 hits might indicate a note was just created/edited on disk outside Echo
                _sync_vault_index(policy, db_path, mode, force=True)
                results = _execute_query(con, query, allowed_prefixes, limit)
            return results
    except Exception as e:
        logger.warning(f"FTS5 search failed ({e}), falling back to linear scan.")
        return _search_vault_linear(policy, query, mode, limit)


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
    title, text, _ = _get_note_content(note.absolute)
    max_chars = max(200, min(int(max_chars), MAX_READ_CHARS))

    # Notes that fit within max_chars are returned completely intact with formatting
    if len(text) <= max_chars:
        return SearchResult(note.relative.as_posix(), title, text)

    # For large notes, extract a relevant window around query if provided
    query = query.strip()
    if query:
        match = re.search(re.escape(query), text, re.IGNORECASE)
        if not match:
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
