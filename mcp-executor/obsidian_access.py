"""Read-only path policy for the Obsidian vault.

This module contains no MCP tools.  Every future Obsidian tool must resolve
paths through :class:`VaultAccessPolicy` before reading anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class AccessMode(StrEnum):
    STANDARD = "standard"
    PRIVATE_ON_DEMAND = "private_on_demand"
    ARCHIVE_ON_DEMAND = "archive_on_demand"


STANDARD_ROOTS = frozenset({"1. Projects", "3. Resources", "5. Note"})
PRIVATE_ROOTS = frozenset({"2. Areas"})
ARCHIVE_ROOTS = frozenset({"4. Archives"})
DENIED_DIRECTORIES = frozenset(
    {
        ".git",
        ".obsidian",
        ".wenbo-agent",
        "_attachments",
        "attachment",
        "attachments",
    }
)
SENSITIVE_NAME_MARKERS = (
    "password",
    "密码",
    "token",
    "secret",
    "恢复码",
    "密钥",
    "private key",
)


@dataclass(frozen=True)
class VaultPath:
    absolute: Path
    relative: Path
    mode: AccessMode


class VaultAccessPolicy:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError("Obsidian Vault 根路径不是目录")

    def resolve_markdown(self, path: Path | str, mode: AccessMode = AccessMode.STANDARD) -> VaultPath:
        resolved, relative = self._resolve(path)
        if not resolved.is_file():
            raise ValueError("目标不是普通文件")
        if resolved.suffix.lower() != ".md":
            raise PermissionError("仅允许读取 Markdown 笔记")
        self._enforce(relative, mode)
        return VaultPath(resolved, relative, mode)

    def resolve_directory(self, path: Path | str, mode: AccessMode = AccessMode.STANDARD) -> VaultPath:
        resolved, relative = self._resolve(path)
        if not resolved.is_dir():
            raise ValueError("目标不是目录")
        self._enforce(relative, mode)
        return VaultPath(resolved, relative, mode)

    def validate_new_markdown(self, path: Path | str, mode: AccessMode = AccessMode.STANDARD) -> VaultPath:
        requested = Path(path)
        if requested.is_absolute():
            raise PermissionError("新笔记必须使用 Vault 内相对路径")
        candidate = (self.root / requested).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise PermissionError("路径越出 Obsidian Vault")
        relative = candidate.relative_to(self.root)
        if candidate.suffix.lower() != ".md":
            raise PermissionError("仅允许创建 Markdown 笔记")
        if candidate.exists():
            raise FileExistsError("目标笔记已存在，拒绝覆盖")
        self._enforce(relative, mode)
        return VaultPath(candidate, relative, mode)

    def _resolve(self, path: Path | str) -> tuple[Path, Path]:
        requested = Path(path)
        if requested.is_absolute():
            candidate = requested
        else:
            candidate = self.root / requested
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError("笔记或目录不存在") from exc
        if not resolved.is_relative_to(self.root):
            raise PermissionError("路径越出 Obsidian Vault")
        return resolved, resolved.relative_to(self.root)

    def _enforce(self, relative: Path, mode: AccessMode) -> None:
        parts = relative.parts
        if not parts:
            raise PermissionError("不允许直接访问 Vault 根目录")

        lowered_parts = tuple(part.casefold() for part in parts)
        if any(part in DENIED_DIRECTORIES or part.startswith(".") for part in lowered_parts):
            raise PermissionError("路径属于永久排除目录")

        filename = parts[-1].casefold()
        if any(marker in filename for marker in SENSITIVE_NAME_MARKERS):
            raise PermissionError("文件名命中敏感信息规则")

        top_level = parts[0]
        if top_level in STANDARD_ROOTS:
            if mode is not AccessMode.STANDARD:
                raise PermissionError("访问模式与普通笔记目录不匹配")
            return
        if top_level in PRIVATE_ROOTS:
            if mode is not AccessMode.PRIVATE_ON_DEMAND:
                raise PermissionError("个人区域仅允许私聊按需访问")
            return
        if top_level in ARCHIVE_ROOTS:
            if mode is not AccessMode.ARCHIVE_ON_DEMAND:
                raise PermissionError("归档仅允许明确按需访问")
            return
        raise PermissionError("路径不在允许的 Obsidian 目录中")
