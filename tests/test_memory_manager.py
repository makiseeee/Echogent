import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).parents[1] / "scripts" / "memory_manager.py"
spec = importlib.util.spec_from_file_location("memory_manager", MODULE)
memory_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memory_manager)

class MemoryManagerTests(unittest.TestCase):
    def test_normalize_ignores_spacing_and_punctuation(self):
        self.assertEqual(memory_manager.normalize("用户 偏好先给结论。"), "用户偏好先给结论")

    def test_high_risk_reduces_score(self):
        base = {"explicit": 1, "stability": 1, "usefulness": 1, "repetition": 3}
        low = memory_manager.candidate_score({**base, "risk": 0})
        high = memory_manager.candidate_score({**base, "risk": 1})
        self.assertGreater(low, high)

    def test_score_is_bounded(self):
        self.assertEqual(memory_manager.candidate_score({"explicit": 9, "stability": 9, "usefulness": 9, "repetition": 9, "risk": 0}), 1.0)
        self.assertEqual(memory_manager.candidate_score({"explicit": 0, "stability": 0, "usefulness": 0, "repetition": 0, "risk": 9}), 0.0)

if __name__ == "__main__":
    unittest.main()
