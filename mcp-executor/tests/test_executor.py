from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path


SERVER_PATH = Path(__file__).resolve().parents[1] / "server.py"
SPEC = importlib.util.spec_from_file_location("echo_mcp_server", SERVER_PATH)
assert SPEC and SPEC.loader
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class PythonSandboxTests(unittest.TestCase):
    def test_expression_result(self):
        result = SERVER._run_python_impl("sum(i * i for i in range(10))", 3)
        self.assertEqual(result, "285")

    def test_math_is_preloaded(self):
        result = SERVER._run_python_impl("round(math.sqrt(2), 6)", 3)
        self.assertEqual(result, "1.414214")

    def test_import_is_rejected(self):
        result = SERVER._run_python_impl("import os\nprint(os.getcwd())", 3)
        self.assertIn("不支持的语法：Import", result)

    def test_reflection_is_rejected(self):
        result = SERVER._run_python_impl("(1).__class__", 3)
        self.assertIn("禁止访问下划线反射属性", result)

    def test_generator_frame_escape_is_rejected(self):
        code = "g = (item for item in ())\ng.gi_frame.f_back"
        result = SERVER._run_python_impl(code, 3)
        self.assertIn("禁止访问下划线反射属性", result)

    def test_timeout(self):
        result = SERVER._run_python_impl("while True:\n    pass", 1)
        self.assertIn("执行超时", result)


class ReadFileTests(unittest.TestCase):
    def test_read_inside_root_and_reject_escape(self):
        with tempfile.TemporaryDirectory() as root:
            allowed = Path(root)
            (allowed / "ok.txt").write_text("hello", encoding="utf-8")
            old = os.environ.get("ECHO_MCP_ALLOWED_ROOTS")
            os.environ["ECHO_MCP_ALLOWED_ROOTS"] = root
            try:
                self.assertEqual(SERVER.read_file("ok.txt"), "hello")
                denied = SERVER.read_file("/etc/passwd")
                self.assertIn("路径不在允许读取的工作区内", denied)
            finally:
                if old is None:
                    os.environ.pop("ECHO_MCP_ALLOWED_ROOTS", None)
                else:
                    os.environ["ECHO_MCP_ALLOWED_ROOTS"] = old


if __name__ == "__main__":
    unittest.main()
