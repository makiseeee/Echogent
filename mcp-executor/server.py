#!/usr/bin/env python3
"""echo 的最小 MCP 执行端。

只提供在线检查、受限 Python 计算和限定目录读取，不开放 shell 或写文件。
"""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import resource
import signal
import socket
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from obsidian_access import AccessMode, VaultAccessPolicy
from obsidian_search import list_notes, read_note_excerpt, search_vault
from obsidian_write import NoteWriteService


BASE_DIR = Path(__file__).resolve().parent
RUNNER_PATH = BASE_DIR / "sandbox_runner.py"
DEFAULT_WORKSPACE = BASE_DIR / "workspace"
MAX_CODE_CHARS = 20_000
MAX_FILE_BYTES = 64 * 1024
MAX_OUTPUT_CHARS = 32_000
MAX_TIMEOUT_SECONDS = 10
MEMORY_LIMIT_BYTES = 256 * 1024 * 1024
OBSIDIAN_MAX_RESULTS = 20
_OBSIDIAN_WRITE_SERVICE: NoteWriteService | None = None


def _allowed_roots() -> tuple[Path, ...]:
    raw = os.environ.get("ECHO_MCP_ALLOWED_ROOTS", str(DEFAULT_WORKSPACE))
    roots = []
    for item in raw.split(os.pathsep):
        if item.strip():
            roots.append(Path(item).expanduser().resolve())
    if not roots:
        roots.append(DEFAULT_WORKSPACE.resolve())
    return tuple(roots)


def _resolve_allowed_file(path: str) -> Path:
    requested = Path(path).expanduser()
    roots = _allowed_roots()
    if not requested.is_absolute():
        requested = roots[0] / requested

    try:
        resolved = requested.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ValueError("文件不存在") from exc

    if not resolved.is_file():
        raise ValueError("目标不是普通文件")
    if not any(resolved.is_relative_to(root) for root in roots):
        raise PermissionError("路径不在允许读取的工作区内")
    return resolved


def _obsidian_policy() -> VaultAccessPolicy:
    raw = os.environ.get("ECHO_OBSIDIAN_VAULT", "").strip()
    if not raw:
        raise RuntimeError("ECHO_OBSIDIAN_VAULT 未配置")
    return VaultAccessPolicy(raw)


def _obsidian_writer() -> NoteWriteService:
    global _OBSIDIAN_WRITE_SERVICE
    if _OBSIDIAN_WRITE_SERVICE is None:
        audit_path = os.environ.get("ECHO_OBSIDIAN_AUDIT_DB", str(BASE_DIR / "obsidian-write-audit.db"))
        _OBSIDIAN_WRITE_SERVICE = NoteWriteService(_obsidian_policy(), audit_path)
    return _OBSIDIAN_WRITE_SERVICE


def _obsidian_mode(scope: str) -> AccessMode:
    try:
        return AccessMode(scope)
    except ValueError as exc:
        raise ValueError("未知的 Obsidian 访问范围") from exc


def _run_python_impl(code: str, timeout_seconds: int = MAX_TIMEOUT_SECONDS) -> str:
    if not isinstance(code, str) or not code.strip():
        return "执行失败：代码不能为空"
    if len(code) > MAX_CODE_CHARS:
        return f"执行失败：代码超过 {MAX_CODE_CHARS} 字符限制"
    if not RUNNER_PATH.is_file():
        return "执行失败：沙盒运行器缺失"

    timeout_seconds = max(1, min(int(timeout_seconds), MAX_TIMEOUT_SECONDS))
    unshare = Path("/usr/bin/unshare")
    if not unshare.is_file():
        return "执行失败：当前系统不支持隔离运行"

    with tempfile.TemporaryDirectory(prefix="echo-mcp-python-") as temp_dir:
        temp_path = Path(temp_dir)
        code_path = temp_path / "main.py"
        code_path.write_text(code, encoding="utf-8")

        command = [
            str(unshare),
            "--user",
            "--map-root-user",
            "--mount",
            "--net",
            "--pid",
            "--fork",
            "--mount-proc",
            sys.executable,
            "-I",
            "-S",
            str(RUNNER_PATH),
            str(code_path),
        ]
        env = {
            "ECHO_SANDBOX_MEMORY_BYTES": str(MEMORY_LIMIT_BYTES),
            "ECHO_SANDBOX_TIMEOUT_SECONDS": str(timeout_seconds),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
            "TMPDIR": temp_dir,
        }

        process = subprocess.Popen(
            command,
            cwd=temp_dir,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.communicate()
            return f"执行超时：已在 {timeout_seconds} 秒后终止"

    stdout = stdout.strip()
    stderr = stderr.strip()
    if process.returncode != 0:
        detail = stderr or stdout or f"子进程退出码 {process.returncode}"
        return f"执行失败：{detail[:MAX_OUTPUT_CHARS]}"
    if not stdout:
        return "执行完成，没有输出"
    return stdout[:MAX_OUTPUT_CHARS]


class BearerAuthMiddleware:
    """为 MCP HTTP 端点增加固定 Bearer token 鉴权。"""

    def __init__(self, app: Any, token: str):
        self.app = app
        self.expected = f"Bearer {token}".encode()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http":
            headers = dict(scope.get("headers", []))
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                response = JSONResponse(
                    {"error": "unauthorized"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


HOST = os.environ.get("ECHO_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("ECHO_MCP_PORT", "8765"))
ALLOWED_HOSTS = [
    value.strip()
    for value in os.environ.get("ECHO_MCP_ALLOWED_HOSTS", "").split(",")
    if value.strip()
]


def _host_patterns(hosts: list[str]) -> list[str]:
    return [f"{host}:*" for host in dict.fromkeys(hosts)]

mcp = FastMCP(
    "echo-executor",
    instructions=(
        "Low-risk computer execution endpoint. It offers health checks, "
        "computation-only Python, and read-only access to an explicitly allowed workspace."
    ),
    host=HOST,
    port=PORT,
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_host_patterns([HOST, "127.0.0.1", "localhost", *ALLOWED_HOSTS]),
        allowed_origins=[
            f"http://{host}:*"
            for host in dict.fromkeys([HOST, "127.0.0.1", "localhost", *ALLOWED_HOSTS])
        ],
    ),
)


@mcp.tool()
def health_check() -> str:
    """检查电脑执行端是否在线；执行任务前可用它确认状态。"""

    payload = {
        "status": "ok",
        "service": "echo-executor",
        "hostname": socket.gethostname(),
        "time_utc": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "sandbox": "user+network+mount+pid namespaces, AST allowlist, rlimits",
        "allowed_roots": [str(path) for path in _allowed_roots()],
    }
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
async def run_python(code: str, timeout_seconds: int = MAX_TIMEOUT_SECONDS) -> str:
    """在隔离环境运行纯计算 Python。

    支持循环、函数、math/statistics/decimal/fractions/json/itertools/functools；
    禁止 import、文件、网络、系统命令和下划线反射属性。默认及最大超时均为 10 秒。
    请用 print 输出结果，或把希望返回的表达式放在代码末尾。
    """

    return await asyncio.to_thread(_run_python_impl, code, timeout_seconds)


@mcp.tool()
def read_file(path: str) -> str:
    """只读文本文件；路径必须位于执行端明确允许的工作区内，最大读取 64 KiB。"""

    try:
        resolved = _resolve_allowed_file(path)
        raw = resolved.read_bytes()
    except (OSError, PermissionError, ValueError) as exc:
        return f"读取失败：{exc}"

    truncated = len(raw) > MAX_FILE_BYTES
    raw = raw[:MAX_FILE_BYTES]
    if b"\x00" in raw:
        return "读取失败：暂不支持二进制文件"
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text += f"\n\n[内容已截断，最多读取 {MAX_FILE_BYTES} 字节]"
    return text


def _verify_obsidian_caller(request: Request) -> None:
    owner_id = os.environ.get("ECHO_OBSIDIAN_OWNER_ID", "").strip()
    if not owner_id:
        raise RuntimeError("ECHO_OBSIDIAN_OWNER_ID 未配置")
    if request.headers.get("x-echo-chat-type") != "private":
        raise PermissionError("Obsidian 仅允许本人私聊访问")
    if not hmac.compare_digest(request.headers.get("x-echo-user-id", ""), owner_id):
        raise PermissionError("发送者不是已授权用户")


async def obsidian_api(request: Request) -> JSONResponse:
    """Private HTTP bridge used by the event-aware phone plugin."""
    try:
        _verify_obsidian_caller(request)
        body = await request.json()
        action = str(body.get("action", ""))
        mode = _obsidian_mode(str(body.get("scope", "standard")))
        policy = _obsidian_policy()
        if action == "search":
            value = [
                result.__dict__
                for result in search_vault(policy, str(body.get("query", "")), mode, body.get("limit", OBSIDIAN_MAX_RESULTS))
            ]
        elif action == "list":
            value = list_notes(policy, str(body.get("path", "1. Projects")), mode, body.get("limit", OBSIDIAN_MAX_RESULTS))
        elif action == "read":
            value = read_note_excerpt(
                policy,
                str(body.get("path", "")),
                mode,
                str(body.get("query", "")),
                body.get("max_chars", 4_000),
            ).__dict__
        elif action == "prepare_create":
            operation = _obsidian_writer().prepare(
                request.headers.get("x-echo-user-id", ""),
                str(body.get("path", "")),
                str(body.get("title", "")),
                str(body.get("content", "")),
                body.get("links") or [],
                body.get("metadata") or {},
            )
            value = {
                "operation_id": operation.operation_id,
                "path": operation.path,
                "links": list(operation.links),
                "expires_at": operation.expires_at.isoformat(),
                "preview": operation.text,
            }
        elif action == "commit_create":
            operation = _obsidian_writer().commit(
                request.headers.get("x-echo-user-id", ""),
                str(body.get("operation_id", "")),
            )
            value = {"created": operation.path, "links": list(operation.links)}
        elif action == "cancel_create":
            operation = _obsidian_writer().cancel(
                request.headers.get("x-echo-user-id", ""),
                str(body.get("operation_id", "")),
            )
            value = {"cancelled": operation.path}
        elif action == "prepare_link":
            operation = _obsidian_writer().prepare_link(
                request.headers.get("x-echo-user-id", ""),
                str(body.get("path", "")),
                str(body.get("link_path", "")),
                str(body.get("placement_hint", "")),
            )
            value = {
                "operation_id": operation.operation_id,
                "path": operation.path,
                "link_path": operation.link_path,
                "insertion": operation.heading,
                "expires_at": operation.expires_at.isoformat(),
            }
        elif action == "commit_link":
            operation = _obsidian_writer().commit_link(
                request.headers.get("x-echo-user-id", ""), str(body.get("operation_id", ""))
            )
            value = {"updated": operation.path, "link": operation.link_path, "insertion": operation.heading}
        elif action == "cancel_link":
            operation = _obsidian_writer().cancel_link(
                request.headers.get("x-echo-user-id", ""), str(body.get("operation_id", ""))
            )
            value = {"cancelled": operation.path}
        else:
            raise ValueError("未知的 Obsidian 操作")
        return JSONResponse({"ok": True, "result": value})
    except (OSError, PermissionError, ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=403)


async def status_api(request: Request) -> JSONResponse:
    payload = {
        "online": True,
        "service": "echo-executor",
        "hostname": socket.gethostname(),
        "capabilities": ["python_sandbox", "workspace_read", "obsidian_read", "obsidian_write"],
        "time_utc": datetime.now(UTC).isoformat(),
    }
    return JSONResponse(payload)


class ObsidianAPIMiddleware:
    """Intercept the private bridge without replacing MCP's ASGI lifespan."""

    def __init__(self, app: Any):
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/status":
            response = await status_api(Request(scope, receive))
            await response(scope, receive, send)
            return
        if scope.get("type") == "http" and scope.get("path") == "/obsidian":
            response = await obsidian_api(Request(scope, receive))
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="echo minimal MCP executor")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="streamable-http",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    DEFAULT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return

    token = os.environ.get("ECHO_MCP_TOKEN", "").strip()
    if len(token) < 32:
        raise SystemExit("ECHO_MCP_TOKEN must contain at least 32 characters")

    import uvicorn

    app = ObsidianAPIMiddleware(mcp.streamable_http_app())
    app = BearerAuthMiddleware(app, token)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
