"""EchoTools 配置、环境与全局路径解析模块。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from core.compat import logger


class PluginConfig:
    """管理 EchoTools 运行期配置与路径解析。"""

    def __init__(self, data_root: Path | None = None) -> None:
        if data_root is None:
            configured = os.environ.get("ECHO_ASTRBOT_DATA", "").strip()
            candidates = [Path(configured)] if configured else []
            candidates.extend([Path("/opt/echo/data"), Path("astrbot/data"), Path("data")])
            found = next((c for c in candidates if c.is_dir()), None)
            self.data_dir = found or Path(configured or "data")
        else:
            self.data_dir = data_root

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.usage_db = self.data_dir / "echo-tools-token-usage.db"
        self.vault_dir = Path(os.environ.get("ECHO_PHONE_VAULT", "/root/obsidiangit"))
        self.audit_db = self.data_dir / "obsidian-write-audit.db"

        # Git 同步配置
        self.git_remote = os.environ.get("ECHO_OBSIDIAN_GIT_REMOTE", "origin")
        self.git_branch = os.environ.get("ECHO_OBSIDIAN_GIT_BRANCH", "main")
        self.git_timeout = int(os.environ.get("ECHO_OBSIDIAN_GIT_TIMEOUT", "30"))
        self.git_username = os.environ.get("ECHO_OBSIDIAN_GIT_USERNAME", "")
        self.git_token = os.environ.get("ECHO_OBSIDIAN_GIT_TOKEN", "")
        self._owner_ids_cache: tuple[Path, float, set[str]] | None = None

    def find_data_file(self, name: str) -> Path:
        """从候选目录解析指定 AstrBot 数据文件（如 cmd_config.json, mcp_server.json）。"""
        candidates = [self.data_dir / name]
        candidates.extend([Path("/opt/echo/data") / name, Path("astrbot/data") / name, Path("data") / name])
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise RuntimeError(f"找不到 AstrBot 配置文件：{name}")

    def get_owner_ids(self) -> set[str]:
        """读取管理员 QQ ID 列表（带有 mtime 缓存）。"""
        try:
            cfg_file = self.find_data_file("cmd_config.json")
            mtime = cfg_file.stat().st_mtime
            if (
                self._owner_ids_cache is not None
                and self._owner_ids_cache[0] == cfg_file
                and self._owner_ids_cache[1] == mtime
            ):
                return self._owner_ids_cache[2]

            data = json.loads(cfg_file.read_text(encoding="utf-8"))
            admins = {str(val) for val in data.get("admins_id", []) if str(val)}
            self._owner_ids_cache = (cfg_file, mtime, admins)
            return admins
        except Exception as exc:
            logger.warning(f"[EchoTools.Config] 读取管理员 ID 失败: {exc}")
            return set()

    def get_daily_cron_session(self) -> str:
        """解析用于晨报/晚报推送的 QQ 私聊会话 ID。"""
        configured = os.environ.get("ECHO_DAILY_SESSION", "").strip()
        if configured:
            return configured

        owner_ids = self.get_owner_ids()
        try:
            db_path = self.find_data_file("data_v4.db")
            with sqlite3.connect(db_path, timeout=5.0) as db:
                for owner_id in owner_ids:
                    row = db.execute(
                        "SELECT user_id FROM conversations "
                        "WHERE user_id LIKE ? ORDER BY updated_at DESC LIMIT 1",
                        (f"%:FriendMessage:{owner_id}",),
                    ).fetchone()
                    if row and row[0]:
                        return str(row[0])
        except (OSError, sqlite3.Error):
            logger.warning("[EchoTools.Config] 无法从会话历史中解析每日任务目标会话")

        if len(owner_ids) == 1:
            return f"echo-qq:FriendMessage:{next(iter(owner_ids))}"
        raise RuntimeError("无法确定每日自动任务的 QQ 私聊会话，请设置 ECHO_DAILY_SESSION")

    def get_obsidian_connection(self) -> tuple[str, str]:
        """读取传统 MCP 连接配置 (备用/回退)。"""
        data = json.loads(self.find_data_file("mcp_server.json").read_text(encoding="utf-8"))
        servers = data.get("mcpServers", {})
        server = servers.get("echo-executor") or servers.get("echo-computer") or next(iter(servers.values()), {})
        url = str(server.get("url", "")).replace("/mcp", "/obsidian")
        headers = server.get("headers", {})
        token = str(headers.get("Authorization", ""))
        if not url or not token:
            raise RuntimeError("echo-computer MCP 地址或令牌未配置")
        return url, token
