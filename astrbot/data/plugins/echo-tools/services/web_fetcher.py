"""Bing 联网搜索与网页内容纯文本抓取服务 (WebFetcher)。"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
import urllib.parse
from typing import Any

import aiohttp
from core.compat import logger
from core.http_client import HttpClient
from lxml import html as lxml_html


def is_safe_public_url(url: str) -> tuple[bool, str]:
    """校验 URL 是否安全可访问，拦截私网/回环/保留/链路本地地址 (SSRF 防御)。"""
    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as exc:
        return False, f"链接解析失败: {exc}"

    if parsed.scheme not in ("http", "https"):
        return False, "链接协议不合法，仅支持 http:// 或 https://"

    hostname = parsed.hostname
    if not hostname:
        return False, "链接缺少有效的主机名"

    host_lower = hostname.lower()
    if host_lower in {"localhost", "ip6-localhost", "ip6-loopback"} or host_lower.endswith(
        (".local", ".internal", ".lan")
    ):
        return False, f"安全拦截：禁止访问内网或本地地址「{hostname}」"

    # 检查是否为域名解析或是直接 IP 访问
    is_domain = False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        is_domain = True

    try:
        addr_info = socket.getaddrinfo(hostname, None)
        lan_networks = (
            ipaddress.ip_network("10.0.0.0/8"),
            ipaddress.ip_network("172.16.0.0/12"),
            ipaddress.ip_network("192.168.0.0/16"),
            ipaddress.ip_network("0.0.0.0/8"),
            ipaddress.ip_network("fc00::/7"),
        )
        fake_ip_pool = ipaddress.ip_network("198.18.0.0/15")

        for info in addr_info:
            ip_str = info[4][0]
            ip = ipaddress.ip_address(ip_str)

            if ip.is_loopback or ip.is_link_local or ip.is_multicast:
                return False, f"安全拦截：目标地址为回环或链路本地 IP ({ip_str})"

            if any(ip in net for net in lan_networks):
                return False, f"安全拦截：目标地址解析为内网私有 IP ({ip_str})"

            # 198.18.0.0/15 是 Clash/Mihomo 的 Fake-IP 虚拟池。
            # 若来源为域名，说明是通过本地代理分发的合法互联网请求；若直接为字面量 IP 则拦截。
            if ip in fake_ip_pool and not is_domain:
                return False, f"安全拦截：禁止直连 Fake-IP 保留测试网段 ({ip_str})"
    except socket.gaierror:
        return False, f"无法解析主机名「{hostname}」，请检查域名是否有效"
    except Exception as exc:  # noqa: BLE001
        return False, f"目标地址校验失败: {exc}"

    return True, ""


def _parse_bing_sync(page: str, limit: int = 5) -> list[tuple[str, str, str]]:
    """从 Bing 结果页解析 title / url / snippet (CPU 密集同步解析)。"""
    doc = lxml_html.fromstring(page)
    results = []
    for li in doc.xpath('//li[contains(@class,"b_algo")]'):
        a = li.xpath(".//h2/a")
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


def _clean_html_sync(page: str) -> str:
    """去除网页导航、脚本与样式，提取纯文本正文 (CPU 密集同步解析)。"""
    doc = lxml_html.fromstring(page)
    for tag in doc.xpath("//script|//style|//noscript|//nav|//footer"):
        tag.drop_tree()
    text = doc.text_content()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:2000] if text else "页面没有可读文本"


class WebFetcher:
    """提供网页内容抓取与 Bing 搜索解析服务（带连接池复用与 SSRF 安全拦截）。"""

    def __init__(self) -> None:
        pass

    async def get_session(self) -> aiohttp.ClientSession:
        """获取或初始化复用的 ClientSession 连接池。"""
        return await HttpClient.get_session()

    async def close(self) -> None:
        """优雅关闭 ClientSession 连接池。"""
        await HttpClient.close()

    async def web_search(self, query: str) -> str:
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
            session = await self.get_session()
            async with session.get(
                url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return f"搜索失败：HTTP {resp.status}"
                page = await resp.text(errors="ignore")
        except Exception as e:  # noqa: BLE001
            logger.error(f"[WebFetcher] web_search error: {e}")
            return f"搜索失败：{e}"

        results = await asyncio.to_thread(_parse_bing_sync, page, 5)
        if not results:
            return "没搜到相关内容，换个关键词试试"

        lines = []
        for idx, (title, link, snippet) in enumerate(results, 1):
            lines.append(f"{idx}. {title}\n{link}\n{snippet}")
        return "\n\n".join(lines)

    async def web_fetch(self, url: str) -> str:
        """抓取网页纯文本内容并去除导航、脚本与样式（带 SSRF 拦截与非阻塞解析）。"""
        is_safe, err_msg = is_safe_public_url(url)
        if not is_safe:
            return err_msg

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
                )
            }
            session = await self.get_session()
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return f"抓取失败：HTTP {resp.status}"
                page = await resp.text(errors="ignore")

            return await asyncio.to_thread(_clean_html_sync, page)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[WebFetcher] web_fetch error: {e}")
            return f"抓取失败：{e}"
