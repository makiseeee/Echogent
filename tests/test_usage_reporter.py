import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

plugin_path = Path('/home/wenbo/aaage/astrbot/data/plugins/echo-tools')
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from services.usage_reporter import UsageReporter


class TestUsageReporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / 'test_usage.db'
        self.reporter = UsageReporter(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_db(self):
        result = self.reporter.get_report('/用量 今日')
        self.assertEqual(result, '暂无 Token 消耗数据记录。')

    def test_empty_db_file_without_table(self):
        self.db_path.touch()
        result = self.reporter.get_report('/用量 今日')
        self.assertEqual(result, '暂无 Token 消耗数据记录。')

    def test_invalid_period(self):
        result = self.reporter.get_report('/用量 明天')
        self.assertIn('用法：', result)

    def test_report_calculation(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                '''
                CREATE TABLE usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    model TEXT,
                    input_other INTEGER,
                    input_cached INTEGER,
                    output INTEGER,
                    total INTEGER,
                    estimated_cost_usd REAL
                )
                '''
            )
            # Insert record for today
            db.execute(
                '''
                INSERT INTO usage (created_at, model, input_other, input_cached, output, total, estimated_cost_usd)
                VALUES (datetime('now', 'localtime'), 'deepseek/deepseek-v4-flash', 1000, 3000, 500, 4500, 0.00035)
                '''
            )
            # Insert record for yesterday
            db.execute(
                '''
                INSERT INTO usage (created_at, model, input_other, input_cached, output, total, estimated_cost_usd)
                VALUES (datetime('now', 'localtime', '-1 day'), 'deepseek/deepseek-v4-flash', 2000, 2000, 1000, 5000, 0.00050)
                '''
            )
            db.commit()

        # Query '今日'
        report_today = self.reporter.get_report('/用量 今日')
        self.assertIn('今日 Token 用量账单统计', report_today)
        self.assertIn('总请求消耗：4,500 tokens', report_today)
        self.assertIn('未缓存输入：1,000', report_today)
        self.assertIn('缓存命中量：3,000（命中率 75.0%）', report_today)
        self.assertIn('API 物理请求：1 次', report_today)

        # Query '全部'
        report_all = self.reporter.get_report('/用量 全部')
        self.assertIn('全部 Token 用量账单统计', report_all)
        self.assertIn('总请求消耗：9,500 tokens', report_all)
        self.assertIn('API 物理请求：2 次', report_all)


if __name__ == '__main__':
    unittest.main()
