"""自适应人格编译器：将 SOUL.md, USER.md, RELATIONSHIP.md 编译注入 AstrBot。"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3

from core.compat import logger
from core.config import PluginConfig


class PersonaCompiler:
    """自动监视并编译人设源文件，热更新至 AstrBot 人格数据库。"""

    @classmethod
    def compile_if_needed(cls, config: PluginConfig | None = None) -> bool:
        """检查并编译人设。若发生更新则返回 True。"""
        try:
            root_candidates = [Path("/opt/echo"), Path("/home/wenbo/aaage"), Path.cwd()]
            root_dir = next(
                (c for c in root_candidates if (c / "SOUL.md").exists() and (c / "USER.md").exists()),
                None,
            )
            if not root_dir:
                return False

            parts = []
            for fname in ("SOUL.md", "USER.md", "RELATIONSHIP.md"):
                fpath = root_dir / fname
                if fpath.exists():
                    lines = [
                        line
                        for line in fpath.read_text(encoding="utf-8").strip().splitlines()
                        if not re.match(r"^#\s+[A-Z_]+\.md", line)
                    ]
                    parts.append("\n".join(lines).strip())

            compiled = "\n\n".join(p for p in parts if p).strip()
            if not compiled:
                return False

            # 1. 写入目标 markdown 文件
            target_md = root_dir / "astrbot" / "echo-persona.md"
            if not target_md.parent.exists():
                target_md = root_dir / "echo-persona.md"
            target_md.write_text(compiled, encoding="utf-8")

            # 2. 同步至 data_v4.db 中的 personas 表
            db_candidates = [
                root_dir / "data" / "data_v4.db",
                root_dir / "astrbot" / "data" / "data_v4.db",
                Path("/opt/echo/data/data_v4.db"),
            ]
            if config:
                db_candidates.insert(0, config.data_dir / "data_v4.db")

            for db_path in db_candidates:
                if db_path.exists():
                    with sqlite3.connect(db_path, timeout=5.0) as con:
                        cur = con.cursor()
                        now_str = datetime.now(timezone.utc).isoformat()
                        tables = [
                            r[0]
                            for r in cur.execute(
                                "SELECT name FROM sqlite_master WHERE type='table'"
                            ).fetchall()
                        ]
                        if "personas" in tables:
                            row = cur.execute(
                                "SELECT id FROM personas WHERE persona_id = 'echo'"
                            ).fetchone()
                            if row:
                                cur.execute(
                                    "UPDATE personas SET system_prompt = ?, updated_at = ? WHERE persona_id = 'echo'",
                                    (compiled, now_str),
                                )
                            else:
                                cur.execute(
                                    "INSERT INTO personas (created_at, updated_at, persona_id, system_prompt, begin_dialogs, sort_order) VALUES (?, ?, 'echo', ?, '[]', 0)",
                                    (now_str, now_str, compiled),
                                )
                            con.commit()

            logger.info("[PersonaCompiler] 自适应人格编译器执行完成，已自动同步最新 SOUL/USER/RELATIONSHIP 人设。")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[PersonaCompiler] 自动编译人格失败: {exc}")
            return False
