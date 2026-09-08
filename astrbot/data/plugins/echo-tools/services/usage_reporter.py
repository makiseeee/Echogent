"""Token 消耗统计与双币种账本生成服务 (UsageReporter)。"""

from __future__ import annotations

from pathlib import Path
import sqlite3


class UsageReporter:
    """查询 SQLite 数据库并格式化 Token 账单统计。"""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get_report(self, message_str: str) -> str:
        """根据用户输入周期（/用量、/用量 今日、/用量 本月、/用量 全部）输出统计报表。"""
        parts = (message_str or "").split()
        period = parts[1] if len(parts) > 1 else "今日"
        if period not in {"今日", "本月", "全部"}:
            return "用法：/用量、/用量 今日、/用量 本月或 /用量 全部"

        where = "1=1"
        args: list[str] = []
        if period == "今日":
            where += " AND created_at >= date('now','localtime')"
        elif period == "本月":
            where += " AND created_at >= strftime('%Y-%m-01','now','localtime')"

        if not self.db_path.exists():
            return "暂无 Token 消耗数据记录。"

        try:
            with sqlite3.connect(self.db_path, timeout=5.0) as db:
                row = db.execute(
                    f"SELECT COUNT(*), COALESCE(SUM(input_other),0), COALESCE(SUM(input_cached),0), "
                    f"COALESCE(SUM(output),0), COALESCE(SUM(total),0), COALESCE(SUM(estimated_cost_usd),0) "
                    f"FROM usage WHERE {where}",
                    args,
                ).fetchone()
        except sqlite3.OperationalError:
            return "暂无 Token 消耗数据记录。"

        if not row:
            return "暂无 Token 消耗数据记录。"

        count, input_other, cached, output, total, cost_usd = row
        cache_rate = (cached / (input_other + cached) * 100) if (input_other + cached) > 0 else 0.0

        return (
            f"📊 {period} Token 用量账单统计（USD）：\n"
            f"• 总请求消耗：{total:,} tokens\n"
            f"• 未缓存输入：{input_other:,}\n"
            f"• 缓存命中量：{cached:,}（命中率 {cache_rate:.1f}%）\n"
            f"• 模型输出量：{output:,}\n"
            f"• API 物理请求：{count} 次\n"
            f"• 预估账单计费：${cost_usd:.5f} USD"
        )
