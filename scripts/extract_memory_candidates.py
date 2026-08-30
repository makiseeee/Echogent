#!/usr/bin/env python3
"""Conservative bridge from daily notes to candidate memory records.

Only explicit user-style memory requests are promoted; all other text stays
in the daily log until an LLM review stage is added.
"""
from __future__ import annotations
import re, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "scripts" / "memory_manager.py"
PATTERNS = [
    re.compile(r"(?:记住|请记住|以后都|以后请|不要再|别再|我喜欢|我不喜欢)[：:，, ]*(.{4,120})"),
]

def main(path: str):
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    found = set()
    for line in text.splitlines():
        line = line.strip(" -*\t")
        for pattern in PATTERNS:
            m = pattern.search(line)
            if m:
                candidate = m.group(0).strip()
                if candidate in found: continue
                found.add(candidate)
                subprocess.run([sys.executable, str(MANAGER), "candidate", candidate,
                                "--type", "explicit_request", "--target", "review",
                                "--explicit", "1", "--stability", "0.7",
                                "--usefulness", "0.7", "--risk", "0"], check=True)
    print(f"extracted {len(found)} explicit candidates")

if __name__ == "__main__":
    if len(sys.argv) != 2: raise SystemExit("usage: extract_memory_candidates.py DAILY.md")
    main(sys.argv[1])
