"""Preview-first, create-only writes for the Obsidian vault."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import threading

try:
    from .obsidian_access import AccessMode, VaultAccessPolicy
    from .obsidian_git import VaultGitSync
    from .obsidian_search import index_single_note, _title
except ImportError:
    from obsidian.obsidian_access import AccessMode, VaultAccessPolicy
    from obsidian.obsidian_git import VaultGitSync
    from obsidian.obsidian_search import index_single_note, _title

MAX_NOTE_CHARS = 20_000
MAX_LINKS = 20
PENDING_TTL = timedelta(minutes=10)


@dataclass(frozen=True)
class PendingNote:
    operation_id: str
    owner_id: str
    path: str
    text: str
    links: tuple[str, ...]
    expires_at: datetime


@dataclass(frozen=True)
class PendingLink:
    operation_id: str
    owner_id: str
    path: str
    link_path: str
    heading: str
    original_hash: str
    updated_text: str
    expires_at: datetime


class NoteWriteService:
    def __init__(self, policy: VaultAccessPolicy, audit_path: Path | str | None = None, git_sync: VaultGitSync | None = None):
        self.policy = policy
        self._pending: dict[str, PendingNote] = {}
        self._pending_links: dict[str, PendingLink] = {}
        self._lock = threading.Lock()
        self.audit_path = Path(audit_path) if audit_path else None
        self.git_sync = git_sync
        if self.audit_path:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.audit_path) as db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS write_audit (
                        id INTEGER PRIMARY KEY,
                        created_at TEXT NOT NULL,
                        owner_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        operation_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        links_count INTEGER NOT NULL,
                        detail TEXT NOT NULL DEFAULT ''
                    )
                """)

    def prepare(
        self,
        owner_id: str,
        path: str,
        title: str,
        content: str,
        links: list[str] | None = None,
        metadata: dict | None = None,
    ) -> PendingNote:
        target = self._new_note_path(path)
        title = title.strip()
        content = content.strip()
        if not title:
            raise ValueError("笔记标题不能为空")
        if not content:
            raise ValueError("笔记正文不能为空")
        if len(content) > MAX_NOTE_CHARS:
            raise ValueError(f"笔记正文超过 {MAX_NOTE_CHARS} 字符限制")

        validated_links = self._validate_links(links or [])
        text = self._render(title, content, validated_links, metadata or {})
        operation = PendingNote(
            operation_id=secrets.token_urlsafe(18),
            owner_id=owner_id,
            path=target.relative_to(self.policy.root).as_posix(),
            text=text,
            links=tuple(validated_links),
            expires_at=datetime.now(UTC) + PENDING_TTL,
        )
        with self._lock:
            self._purge_expired()
            self._pending[operation.operation_id] = operation
        self._audit(operation, "prepared")
        return operation

    def commit(self, owner_id: str, operation_id: str) -> PendingNote:
        if self.git_sync:
            operation, _ = self.git_sync.atomic_write(
                lambda: self._commit_local(owner_id, operation_id),
                "create Obsidian note",
            )
            return operation
        return self._commit_local(owner_id, operation_id)

    def _commit_local(self, owner_id: str, operation_id: str) -> PendingNote:
        with self._lock:
            self._purge_expired()
            operation = self._pending.get(operation_id)
            if operation is None:
                raise ValueError("待确认操作不存在或已过期")
            if operation.owner_id != owner_id:
                raise PermissionError("待确认操作不属于当前用户")
            target = self._new_note_path(operation.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                with target.open("x", encoding="utf-8") as handle:
                    handle.write(operation.text)
            except FileExistsError as exc:
                raise FileExistsError("目标笔记已存在，拒绝覆盖") from exc
            del self._pending[operation_id]
            title = _title(target, operation.text)
            index_single_note(self.policy, operation.path, title, operation.text)
        self._audit(operation, "committed")
        return operation

    def cancel(self, owner_id: str, operation_id: str) -> PendingNote:
        with self._lock:
            operation = self._pending.get(operation_id)
            if operation is None:
                raise ValueError("待确认操作不存在或已过期")
            if operation.owner_id != owner_id:
                raise PermissionError("待确认操作不属于当前用户")
            del self._pending[operation_id]
        self._audit(operation, "cancelled")
        return operation

    def prepare_link(
        self,
        owner_id: str,
        path: str,
        link_path: str,
        placement_hint: str = "",
    ) -> PendingLink:
        note = self.policy.resolve_markdown(path, AccessMode.STANDARD)
        linked = self.policy.resolve_markdown(link_path, AccessMode.STANDARD)
        text = note.absolute.read_text(encoding="utf-8")
        wikilink = f"[[{linked.relative.with_suffix('').as_posix()}]]"
        if wikilink in text:
            raise ValueError("目标笔记已包含该链接")
        heading, updated = self._insert_link(text, wikilink, placement_hint)
        operation = PendingLink(
            operation_id=secrets.token_urlsafe(18),
            owner_id=owner_id,
            path=note.relative.as_posix(),
            link_path=linked.relative.as_posix(),
            heading=heading,
            original_hash=self._hash(text),
            updated_text=updated,
            expires_at=datetime.now(UTC) + PENDING_TTL,
        )
        with self._lock:
            self._purge_expired()
            self._pending_links[operation.operation_id] = operation
        self._audit_link(operation, "link_prepared")
        return operation

    def commit_link(self, owner_id: str, operation_id: str) -> PendingLink:
        if self.git_sync:
            operation, _ = self.git_sync.atomic_write(
                lambda: self._commit_link_local(owner_id, operation_id),
                "link Obsidian notes",
            )
            return operation
        return self._commit_link_local(owner_id, operation_id)

    def _commit_link_local(self, owner_id: str, operation_id: str) -> PendingLink:
        with self._lock:
            self._purge_expired()
            operation = self._pending_links.get(operation_id)
            if operation is None:
                raise ValueError("待确认链接操作不存在或已过期")
            if operation.owner_id != owner_id:
                raise PermissionError("待确认操作不属于当前用户")
            note = self.policy.resolve_markdown(operation.path, AccessMode.STANDARD)
            current = note.absolute.read_text(encoding="utf-8")
            if self._hash(current) != operation.original_hash:
                raise RuntimeError("旧笔记在预览后发生变化，请重新生成预览")
            backup_root = self.audit_path.parent / "obsidian-backups" if self.audit_path else note.absolute.parent
            backup = backup_root / datetime.now().strftime("%Y%m%d-%H%M%S") / operation.path
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_text(current, encoding="utf-8")
            temp = note.absolute.with_name(f".{note.absolute.name}.{secrets.token_hex(6)}.tmp")
            temp.write_text(operation.updated_text, encoding="utf-8")
            temp.replace(note.absolute)
            del self._pending_links[operation_id]
            title = _title(note.absolute, operation.updated_text)
            index_single_note(self.policy, operation.path, title, operation.updated_text)
        self._audit_link(operation, "link_committed", f"backup={backup}")
        return operation

    def cancel_link(self, owner_id: str, operation_id: str) -> PendingLink:
        with self._lock:
            operation = self._pending_links.get(operation_id)
            if operation is None:
                raise ValueError("待确认链接操作不存在或已过期")
            if operation.owner_id != owner_id:
                raise PermissionError("待确认操作不属于当前用户")
            del self._pending_links[operation_id]
        self._audit_link(operation, "link_cancelled")
        return operation

    def _new_note_path(self, path: str) -> Path:
        requested = Path(path)
        validated = self.policy.validate_new_markdown(requested, AccessMode.STANDARD)
        candidate = validated.absolute
        parent = candidate.parent
        while not parent.exists() and parent != self.policy.root:
            parent = parent.parent
        self.policy.resolve_directory(parent, AccessMode.STANDARD)
        return candidate

    def _validate_links(self, links: list[str]) -> list[str]:
        if len(links) > MAX_LINKS:
            raise ValueError(f"关联笔记不能超过 {MAX_LINKS} 条")
        result = []
        for link in links:
            note = self.policy.resolve_markdown(link, AccessMode.STANDARD)
            result.append(note.relative.as_posix())
        return list(dict.fromkeys(result))

    @staticmethod
    def _render(title: str, content: str, links: list[str], metadata: dict) -> str:
        frontmatter = {"created": datetime.now().astimezone().date().isoformat(), **metadata}
        lines = ["---"]
        for key, value in frontmatter.items():
            if not isinstance(key, str) or not key or "\n" in key:
                raise ValueError("YAML 属性名无效")
            if not isinstance(value, (str, int, float, bool, list)) and value is not None:
                raise ValueError("YAML 属性值类型不受支持")
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.extend(["---", "", f"# {title}", "", content])
        if links:
            lines.extend(["", "## 相关笔记", ""])
            lines.extend(f"- [[{Path(link).with_suffix('').as_posix()}]]" for link in links)
        return "\n".join(lines).rstrip() + "\n"

    def _purge_expired(self) -> None:
        now = datetime.now(UTC)
        expired = [value for value in self._pending.values() if value.expires_at <= now]
        self._pending = {key: value for key, value in self._pending.items() if value.expires_at > now}
        for operation in expired:
            self._audit(operation, "expired")
        expired_links = [value for value in self._pending_links.values() if value.expires_at <= now]
        self._pending_links = {key: value for key, value in self._pending_links.items() if value.expires_at > now}
        for operation in expired_links:
            self._audit_link(operation, "link_expired")

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _insert_link(text: str, wikilink: str, hint: str) -> tuple[str, str]:
        lines = text.splitlines()
        headings = [(index, line.lstrip("# ").strip()) for index, line in enumerate(lines) if line.startswith("## ")]
        preferred = ("相关笔记", "关联笔记", "相关内容", "关联项目", "see also", "references")
        hint_words = [word.casefold() for word in hint.replace("/", " ").split() if len(word) >= 2]
        selected = None
        for index, heading in headings:
            folded = heading.casefold()
            if hint_words and any(word in folded for word in hint_words):
                selected = (index, heading)
                break
        if selected is None:
            for index, heading in headings:
                if any(name in heading.casefold() for name in preferred):
                    selected = (index, heading)
                    break
        link_line = f"- {wikilink}"
        if selected is None:
            updated = text.rstrip() + f"\n\n## 相关笔记\n\n{link_line}\n"
            return "新建 ## 相关笔记", updated
        start, heading = selected
        end = next((index for index, _ in headings if index > start), len(lines))
        insert_at = end
        while insert_at > start + 1 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, link_line)
        return f"## {heading}", "\n".join(lines).rstrip() + "\n"

    def _audit(self, operation: PendingNote, action: str, detail: str = "") -> None:
        if not self.audit_path:
            return
        with sqlite3.connect(self.audit_path) as db:
            db.execute(
                "INSERT INTO write_audit(created_at,owner_id,action,operation_id,path,links_count,detail) VALUES(?,?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), operation.owner_id, action, operation.operation_id, operation.path, len(operation.links), detail),
            )

    def _audit_link(self, operation: PendingLink, action: str, detail: str = "") -> None:
        if not self.audit_path:
            return
        with sqlite3.connect(self.audit_path) as db:
            db.execute(
                "INSERT INTO write_audit(created_at,owner_id,action,operation_id,path,links_count,detail) VALUES(?,?,?,?,?,?,?)",
                (datetime.now(UTC).isoformat(), operation.owner_id, action, operation.operation_id, operation.path, 1, f"link={operation.link_path}; heading={operation.heading}; {detail}"),
            )
