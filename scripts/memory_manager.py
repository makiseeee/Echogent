#!/usr/bin/env python3
"""Small, auditable memory candidate store for Echo.

This stage never edits SOUL.md, USER.md, RELATIONSHIP.md, or MEMORY.md.
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEMORY = ROOT / "memory"
CANDIDATES = MEMORY / "candidates.jsonl"
CONFLICTS = MEMORY / "conflicts.jsonl"
CURRENT = MEMORY / "current.md"
VALID_TARGETS = {"SOUL.md", "USER.md", "RELATIONSHIP.md", "MEMORY.md", "memory/current.md", "daily", "knowledge", "discard", "review"}

def now(): return datetime.now().astimezone().isoformat(timespec="seconds")

def append_jsonl(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def read_jsonl(path: Path):
    if not path.exists(): return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: continue
    return rows

def normalize(text: str) -> str:
    return "".join(text.lower().split()).strip("，。！？,.!?;；：:")

def candidate_score(item: dict) -> float:
    explicit = float(item.get("explicit", 0.0))
    stability = float(item.get("stability", 0.0))
    usefulness = float(item.get("usefulness", 0.0))
    repetition = min(float(item.get("repetition", 1.0)), 3.0) / 3.0
    risk = float(item.get("risk", 0.0))
    return round(max(0.0, min(1.0, .30 * explicit + .25 * stability + .25 * usefulness + .20 * repetition - .35 * risk)), 3)

def find_duplicate(content: str):
    key = normalize(content)
    for row in reversed(read_jsonl(CANDIDATES)):
        old = normalize(row.get("content", ""))
        if key == old or (len(key) >= 12 and (key in old or old in key)):
            return row
    return None

def cmd_candidate(args):
    duplicate = find_duplicate(args.content)
    if duplicate:
        print(f"duplicate:{duplicate['id']}")
        return
    target = args.target if args.target in VALID_TARGETS else "review"
    score = candidate_score({"explicit": args.explicit, "stability": args.stability,
                             "usefulness": args.usefulness, "repetition": args.repetition, "risk": args.risk})
    item = {
        "id": args.id or f"candidate-{date.today():%Y%m%d}-{uuid.uuid4().hex[:8]}",
        "content": args.content,
        "type": args.type,
        "target": target,
        "confidence": args.confidence if args.confidence is not None else score,
        "score": score,
        "signals": {"explicit": args.explicit, "stability": args.stability,
                    "usefulness": args.usefulness, "repetition": args.repetition, "risk": args.risk},
        "status": "pending",
        "source": args.source or f"session:{date.today().isoformat()}",
        "created_at": now(),
        "updated_at": now(),
        "expires_at": (date.today() + timedelta(days=args.ttl)).isoformat() if args.ttl else None,
        "reason": args.reason or "",
    }
    append_jsonl(CANDIDATES, item)
    print(item["id"])

def cmd_expire(_args):
    rows = read_jsonl(CANDIDATES); today = date.today(); changed = 0
    for row in rows:
        expires = row.get("expires_at")
        if row.get("status") == "pending" and expires and date.fromisoformat(expires) < today:
            row["status"] = "expired"; row["updated_at"] = now(); changed += 1
    CANDIDATES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(changed)

def cmd_conflict(args):
    item = {"id": args.id or f"conflict-{date.today():%Y%m%d}-{uuid.uuid4().hex[:8]}",
            "topic": args.topic, "old": args.old, "new": args.new,
            "status": "open", "source": args.source or f"session:{date.today().isoformat()}",
            "created_at": now()}
    append_jsonl(CONFLICTS, item)
    print(item["id"])

def cmd_list(args):
    rows = read_jsonl(CANDIDATES)
    if args.status != "all": rows = [r for r in rows if r.get("status") == args.status]
    for r in rows:
        print(f"{r['id']} [{r.get('status')}] {r.get('target')} c={r.get('confidence')}: {r.get('content')}")

def cmd_decide(args):
    rows = read_jsonl(CANDIDATES)
    found = False
    for r in rows:
        if r.get("id") == args.id:
            r["status"] = args.status
            r["updated_at"] = now()
            if args.note: r["decision_note"] = args.note
            found = True
    if not found: raise SystemExit(f"未找到候选：{args.id}")
    CANDIDATES.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{args.id}: {args.status}")

def cmd_current(args):
    text = args.text.strip()
    CURRENT.write_text(f"# 当前工作记忆\n\n> 自动日更层，内容可过期，不等同于长期记忆。\n\n"
                       f"更新时间：{now()}\n\n## 今日状态\n\n{text}\n\n"
                       "## 记忆边界\n\n当前状态不会自动升级到核心人格、用户画像或关系记忆。\n",
                       encoding="utf-8")
    print(CURRENT)

def build_parser():
    p = argparse.ArgumentParser(description="Echo 分层记忆候选管理器")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("candidate", help="写入一个待审核候选")
    c.add_argument("content"); c.add_argument("--type", default="unknown")
    c.add_argument("--target", default="review")
    c.add_argument("--confidence", type=float)
    c.add_argument("--explicit", type=float, default=0.5)
    c.add_argument("--stability", type=float, default=0.5)
    c.add_argument("--usefulness", type=float, default=0.5)
    c.add_argument("--repetition", type=int, default=1)
    c.add_argument("--risk", type=float, default=0.0)
    c.add_argument("--source"); c.add_argument("--reason"); c.add_argument("--ttl", type=int, default=0)
    c.add_argument("--id"); c.set_defaults(func=cmd_candidate)
    c = sub.add_parser("conflict", help="记录冲突，不静默覆盖")
    c.add_argument("topic"); c.add_argument("old"); c.add_argument("new"); c.add_argument("--source"); c.add_argument("--id")
    c.set_defaults(func=cmd_conflict)
    c = sub.add_parser("list", help="查看候选")
    c.add_argument("--status", default="pending", choices=["pending", "approved", "rejected", "expired", "all"]); c.set_defaults(func=cmd_list)
    c = sub.add_parser("decide", help="审核候选")
    c.add_argument("id"); c.add_argument("status", choices=["approved", "rejected", "expired"]); c.add_argument("--note"); c.set_defaults(func=cmd_decide)
    c = sub.add_parser("current", help="更新每日 current.md")
    c.add_argument("text"); c.set_defaults(func=cmd_current)
    c = sub.add_parser("expire", help="将到期候选标为 expired")
    c.set_defaults(func=cmd_expire)
    return p

if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
