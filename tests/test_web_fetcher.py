import asyncio
from pathlib import Path
import sys
import unittest

plugin_path = Path("/home/wenbo/aaage/astrbot/data/plugins/echo-tools")
if str(plugin_path) not in sys.path:
    sys.path.insert(0, str(plugin_path))

from services.web_fetcher import WebFetcher, _clean_html_sync, is_safe_public_url


class TestWebFetcher(unittest.IsolatedAsyncioTestCase):
    def test_ssrf_blocking_private_and_loopback(self):
        # Localhost & Loopback
        is_safe, msg = is_safe_public_url("http://127.0.0.1:8765/status")
        self.assertFalse(is_safe)
        self.assertIn("安全拦截", msg)

        is_safe, msg = is_safe_public_url("http://localhost:8080")
        self.assertFalse(is_safe)
        self.assertIn("安全拦截", msg)

        # Private Class A (10.0.0.0/8)
        is_safe, msg = is_safe_public_url("http://10.144.232.236:8766/api/pc/activity")
        self.assertFalse(is_safe)
        self.assertIn("安全拦截", msg)

        # Private Class C (192.168.0.0/16)
        is_safe, msg = is_safe_public_url("http://192.168.1.1/admin")
        self.assertFalse(is_safe)
        self.assertIn("安全拦截", msg)

        # Link local (169.254.0.0/16)
        is_safe, msg = is_safe_public_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(is_safe)
        self.assertIn("安全拦截", msg)

        # Invalid schemes
        is_safe, msg = is_safe_public_url("file:///etc/passwd")
        self.assertFalse(is_safe)
        self.assertIn("协议不合法", msg)

        # Public URLs
        is_safe, msg = is_safe_public_url("https://www.bing.com")
        self.assertTrue(is_safe)
        self.assertEqual(msg, "")

    def test_clean_html_sync(self):
        sample_html = """
        <html>
            <head><style>body { color: red; }</style></head>
            <body>
                <nav><a href="/">Home</a></nav>
                <script>alert("xss")</script>
                <h1>Hello Echo</h1>
                <p>This is a test paragraph for non-blocking parsing.</p>
                <footer>Copyright 2026</footer>
            </body>
        </html>
        """
        cleaned = _clean_html_sync(sample_html)
        self.assertIn("Hello Echo", cleaned)
        self.assertIn("This is a test paragraph", cleaned)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("color: red", cleaned)
        self.assertNotIn("Copyright", cleaned)

    async def test_session_management(self):
        fetcher = WebFetcher()
        session1 = await fetcher.get_session()
        session2 = await fetcher.get_session()
        self.assertIs(session1, session2)
        await fetcher.close()
        self.assertTrue(session1.closed)


if __name__ == "__main__":
    unittest.main()
