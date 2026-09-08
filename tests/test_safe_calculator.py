import unittest
import sys
from pathlib import Path

plugin_path = Path(__file__).resolve().parent.parent / "astrbot" / "data" / "plugins" / "echo-tools"
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from services.safe_calculator import SafeCalculator


class TestSafeCalculator(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(SafeCalculator.safe_eval("1 + 2"), 3)
        self.assertEqual(SafeCalculator.safe_eval("10 - 4 * 2"), 2)
        self.assertEqual(SafeCalculator.safe_eval("(12 + 34) * 5 / 2"), 115)
        self.assertEqual(SafeCalculator.safe_eval("2^10"), 1024)
        self.assertEqual(SafeCalculator.safe_eval("2**10"), 1024)

    def test_math_functions_and_constants(self):
        self.assertAlmostEqual(SafeCalculator.safe_eval("sqrt(144)"), 12)
        self.assertAlmostEqual(SafeCalculator.safe_eval("sin(0)"), 0)
        self.assertAlmostEqual(SafeCalculator.safe_eval("cos(0)"), 1)
        self.assertAlmostEqual(SafeCalculator.safe_eval("pi"), 3.141592653589793)
        self.assertEqual(SafeCalculator.safe_eval("abs(-42)"), 42)
        self.assertEqual(SafeCalculator.safe_eval("round(3.7)"), 4)

    def test_security_rejections(self):
        # Disallow imports, system calls, and arbitrary attributes
        with self.assertRaises(ValueError):
            SafeCalculator.safe_eval("__import__('os').system('ls')")
        with self.assertRaises(ValueError):
            SafeCalculator.safe_eval("open('/etc/passwd')")
        with self.assertRaises(ValueError):
            SafeCalculator.safe_eval("[x for x in range(10)]")
        with self.assertRaises(ValueError):
            SafeCalculator.safe_eval("eval('1+1')")

    def test_evaluate_string_output(self):
        self.assertEqual(SafeCalculator.evaluate("10 + 5"), "10 + 5 = 15")
        self.assertTrue(SafeCalculator.evaluate("1/0").startswith("计算失败"))
