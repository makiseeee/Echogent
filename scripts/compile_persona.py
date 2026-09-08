#!/usr/bin/env python3
"""
Persona Compiler for Echo
Merges SOUL.md, USER.md, RELATIONSHIP.md into a single canonical system prompt
and synchronizes it directly to AstrBot SQLite database (data_v4.db).
"""
import sys, os, sqlite3, re
from pathlib import Path
from datetime import datetime, timezone

def find_root() -> Path:
    # Check current dir, phone /opt/echo, or WSL /home/wenbo/aaage
    candidates = [
        Path("/opt/echo"),
        Path("/home/wenbo/aaage"),
        Path(__file__).resolve().parent.parent,
        Path.cwd()
    ]
    for c in candidates:
        if (c / "SOUL.md").exists() and (c / "USER.md").exists():
            return c
    return Path.cwd()

def clean_doc(content: str) -> str:
    # Strip top H1 headers like '# SOUL.md - ...'
    lines = content.strip().splitlines()
    cleaned = []
    for line in lines:
        if re.match(r"^#\s+[A-Z_]+\.md", line):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()

def compile_persona(root_dir: Path) -> str:
    soul_file = root_dir / "SOUL.md"
    user_file = root_dir / "USER.md"
    rel_file = root_dir / "RELATIONSHIP.md"
    
    parts = []
    if soul_file.exists():
        parts.append(clean_doc(soul_file.read_text(encoding="utf-8")))
    if user_file.exists():
        parts.append(clean_doc(user_file.read_text(encoding="utf-8")))
    if rel_file.exists():
        parts.append(clean_doc(rel_file.read_text(encoding="utf-8")))
    
    compiled = "\n\n".join(p for p in parts if p).strip()
    return compiled

def sync_to_db(db_path: Path, system_prompt: str) -> bool:
    if not db_path.exists():
        print(f"[PersonaCompiler] ⚠️ Database not found at {db_path}")
        return False
    try:
        con = sqlite3.connect(db_path, timeout=5.0)
        cur = con.cursor()
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Check if personas table exists
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "personas" not in tables:
            print("[PersonaCompiler] ⚠️ 'personas' table does not exist yet.")
            con.close()
            return False
        
        row = cur.execute("SELECT id FROM personas WHERE persona_id = 'echo'").fetchone()
        if row:
            cur.execute(
                "UPDATE personas SET system_prompt = ?, updated_at = ? WHERE persona_id = 'echo'",
                (system_prompt, now_str)
            )
            print(f"[PersonaCompiler] ✅ Successfully updated persona 'echo' in {db_path}")
        else:
            cur.execute(
                "INSERT INTO personas (created_at, updated_at, persona_id, system_prompt, begin_dialogs, sort_order) VALUES (?, ?, 'echo', ?, '[]', 0)",
                (now_str, now_str, system_prompt)
            )
            print(f"[PersonaCompiler] ✅ Inserted new persona 'echo' into {db_path}")
        con.commit()
        con.close()
        return True
    except Exception as e:
        print(f"[PersonaCompiler] ❌ Failed to update db {db_path}: {e}")
        return False

def main():
    root = find_root()
    print(f"[PersonaCompiler] Using root directory: {root}")
    compiled = compile_persona(root)
    
    # Save to astrbot/echo-persona.md for tracking
    target_md = root / "astrbot" / "echo-persona.md"
    if not target_md.parent.exists():
        target_md = root / "echo-persona.md"
    target_md.write_text(compiled, encoding="utf-8")
    print(f"[PersonaCompiler] 📝 Wrote compiled prompt ({len(compiled)} chars) to {target_md}")
    
    # Sync to local DB candidates
    db_candidates = [
        root / "data" / "data_v4.db",
        root / "astrbot" / "data" / "data_v4.db",
        Path("/opt/echo/data/data_v4.db")
    ]
    for db in db_candidates:
        if db.exists():
            sync_to_db(db, compiled)

if __name__ == "__main__":
    main()
