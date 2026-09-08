from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

plugin_path = Path("/home/wenbo/aaage/astrbot/data/plugins/echo-tools")
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from core.token_interceptor import TokenInterceptor


class TestTokenInterceptor(unittest.TestCase):
    def test_estimate_cost_deepseek_v4_flash(self):
        # Peak: UTC 02:00
        dt_peak = datetime(2026, 9, 8, 2, 0, 0, tzinfo=timezone.utc)
        cost_peak = TokenInterceptor.estimate_cost(
            model="deepseek/deepseek-v4-flash",
            input_other=1_000_000,
            input_cached=1_000_000,
            output=1_000_000,
            created_at=dt_peak,
        )
        # rate_in=0.44, rate_cached=0.014, rate_out=1.32
        self.assertAlmostEqual(cost_peak, 0.44 + 0.014 + 1.32, places=4)

        # Off-peak: UTC 12:00
        dt_offpeak = datetime(2026, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        cost_offpeak = TokenInterceptor.estimate_cost(
            model="deepseek/deepseek-v4-flash",
            input_other=1_000_000,
            input_cached=1_000_000,
            output=1_000_000,
            created_at=dt_offpeak,
        )
        # rate_in=0.22, rate_cached=0.007, rate_out=0.66
        self.assertAlmostEqual(cost_offpeak, 0.22 + 0.007 + 0.66, places=4)

    def test_estimate_cost_glm_and_free(self):
        # GLM-5.3-Flash: in 0.15, cached 0.03, out 0.50
        cost_glm = TokenInterceptor.estimate_cost(
            model="z-ai/glm-5.3-flash",
            input_other=1_000_000,
            input_cached=1_000_000,
            output=1_000_000,
        )
        self.assertAlmostEqual(cost_glm, 0.15 + 0.03 + 0.50, places=4)

        # Free model
        cost_free = TokenInterceptor.estimate_cost(
            model="longcat/free-v1",
            input_other=1_000_000,
            input_cached=1_000_000,
            output=1_000_000,
        )
        self.assertEqual(cost_free, 0.0)

    def test_record_api_usage_to_sqlite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "usage.db"
            TokenInterceptor.ensure_database(db_path)

            mock_completion = MagicMock()
            mock_completion.model = "deepseek/deepseek-v4-flash"
            mock_usage = MagicMock()
            mock_usage.prompt_tokens = 5000
            mock_usage.completion_tokens = 800
            mock_usage.total_tokens = 5800
            # Cached tokens detail
            mock_details = MagicMock()
            mock_details.cached_tokens = 3000
            mock_usage.prompt_tokens_details = mock_details
            mock_completion.usage = mock_usage

            TokenInterceptor.record_api_usage(db_path, mock_completion)

            with sqlite3.connect(db_path) as db:
                rows = db.execute(
                    "SELECT model, input_other, input_cached, output, total, estimated_cost_usd FROM usage"
                ).fetchall()
                self.assertEqual(len(rows), 1)
                model, in_other, in_cached, out_tok, total, cost = rows[0]
                self.assertEqual(model, "deepseek/deepseek-v4-flash")
                self.assertEqual(in_other, 2000)
                self.assertEqual(in_cached, 3000)
                self.assertEqual(out_tok, 800)
                self.assertEqual(total, 5800)
                self.assertGreater(cost, 0.0)


if __name__ == "__main__":
    unittest.main()
