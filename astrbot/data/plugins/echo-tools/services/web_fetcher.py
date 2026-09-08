"""Bing 联网搜索与网页内容纯文本抓取服务 (WebFetcher)。"""

from __future__ import annotations

import re
from typing import Any

import aiohttp
from core.compat import logger
from lxml import html as lxml_html


class WebFetcher:
    """提供网页内容抓取与 Bing 搜索解析服务。"""

    @staticmethod
    def parse_bing(page: str, limit: int = 5) -> list[tuple[str, str, str]]:
        """从 Bing 结果页解析 title / url / snippet。"""
        doc = lxml_html.fromstring(page)
        results = []
        for li in doc.xpath('//li[contains(@class,"b_algo")]'):
            a = li.xpath('.//h2/a')
            if not a:
                continue
            title = a[0].text_content().strip()
            href = a[0].get("href", "")
            p = li.xpath(".//p")
            snippet = p[0].text_content().strip() if p else ""
            results.append((title, href, snippet))
            if len(results) >= limit:
                break
        return results

    @classmethod
    async def web_search(cls, query: str) -> str:
        """搜索互联网获取最新信息。"""
        try:
            url = "https://www.bing.com/search"
            params = {"q": query, "setlang": "zh-hans", "cc": "CN"}
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        return f"搜索失败：HTTP {resp.status}"
                    page = await resp.text(errors="ignore")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[WebFetcher] web_search error: {e}")
            return f"搜索失败：{e}"

        results = cls.parse_bing(page, limit=5)
        if not results:
            return "没搜到相关内容，换个关键词试试"

        lines = []
        for idx, (title, link, snippet) in enumerate(results, 1):
            lines.append(f"{idx}. {title}\n{link}\n{snippet}")
        return "\n\n".join(lines)

    @staticmethod
    async def web_fetch(url: str) -> str:
        """抓取网页纯文本内容并去除导航、脚本与样式。"""
        if not url.startswith(("http://", "https://")):
            return "链接格式不对，需要以 http:// 或 https:// 开头"
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        return f"抓取失败：HTTP {resp.status}"
                    page = await resp.text(errors="ignore")
            doc = lxml_html.fromstring(page)
            for tag in doc.xpath("//script|//style|//noscript|//nav|//footer"):
                tag.drop_tree()
            text = doc.text_content()
            text = re.sub(r"\s+", " ", text).strip()
            return text[:2000] if text else "页面没有可读文本"
        except Exception as e:  # noqa: BLE001
            logger.error(f"[WebFetcher] web_fetch error: {e}")
            return f"抓取失败：{e}"
