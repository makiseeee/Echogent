"""全局共享 aiohttp.ClientSession 连接池管理器。

消除重复创建与销毁 ClientSession 带来的 TCP 握手与 TLS 协商开销，支持长连接复用与优雅退出。
"""

from __future__ import annotations

import asyncio
import aiohttp
from core.compat import logger


class HttpClient:
    """管理 Echo 插件生命周期内的全局复用 aiohttp.ClientSession。"""

    _session: aiohttp.ClientSession | None = None
    _lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """获取或初始化全局共享的 ClientSession。"""
        if cls._session is not None and not cls._session.closed:
            return cls._session

        async with cls._get_lock():
            if cls._session is None or cls._session.closed:
                connector = aiohttp.TCPConnector(
                    limit=30,
                    limit_per_host=10,
                    ttl_dns_cache=300,
                    enable_cleanup_closed=True,
                )
                cls._session = aiohttp.ClientSession(connector=connector)
                logger.debug("[HttpClient] 全局 aiohttp.ClientSession 连接池已建立")
            return cls._session

    @classmethod
    async def close(cls) -> None:
        """安全关闭全局 ClientSession。"""
        async with cls._get_lock():
            if cls._session is not None and not cls._session.closed:
                await cls._session.close()
                cls._session = None
                logger.debug("[HttpClient] 全局 aiohttp.ClientSession 连接池已关闭")
