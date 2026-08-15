#!/usr/bin/env python3
"""在隔离子进程中校验并执行纯计算 Python。"""

from __future__ import annotations

import ast
import decimal
import fractions
import functools
import io
import itertools
import json
import math
import os
import resource
import statistics
import sys
from pathlib import Path


OUTPUT_LIMIT = 32_000
DENIED_NODES = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Import,
    ast.ImportFrom,
    ast.With,
)
DENIED_CALLS = {
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
    "__import__",
}
DENIED_ATTRIBUTE_PREFIXES = (
    "ag_",  # async generator internals
    "co_",  # code object internals
    "cr_",  # coroutine internals
    "f_",   # frame internals
    "gi_",  # generator internals
    "tb_",  # traceback internals
)


class CodeValidator(ast.NodeVisitor):
    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, DENIED_NODES):
            raise ValueError(f"不支持的语法：{type(node).__name__}")
        super().generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_") or node.attr.startswith(
            DENIED_ATTRIBUTE_PREFIXES
        ):
            raise ValueError("禁止访问下划线反射属性")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            raise ValueError("禁止使用双下划线名称")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in DENIED_CALLS:
            raise ValueError(f"禁止调用：{node.func.id}")
        self.generic_visit(node)


class LimitedWriter(io.TextIOBase):
    def __init__(self, limit: int):
        self.limit = limit
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def writable(self) -> bool:
        return True

    def write(self, value: str) -> int:
        value = str(value)
        remaining = self.limit - self.length
        if remaining > 0:
            chunk = value[:remaining]
            self.parts.append(chunk)
            self.length += len(chunk)
        if len(value) > max(remaining, 0):
            self.truncated = True
        return len(value)

    def getvalue(self) -> str:
        text = "".join(self.parts)
        if self.truncated:
            text += "\n[输出已截断]"
        return text


SAFE_BUILTINS = {
    "Exception": Exception,
    "ValueError": ValueError,
    "TypeError": TypeError,
    "ZeroDivisionError": ZeroDivisionError,
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "bytes": bytes,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "hash": hash,
    "hex": hex,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def apply_resource_limits() -> None:
    timeout_seconds = max(1, int(os.environ.get("ECHO_SANDBOX_TIMEOUT_SECONDS", "10")))
    memory_bytes = max(
        64 * 1024 * 1024,
        int(os.environ.get("ECHO_SANDBOX_MEMORY_BYTES", str(256 * 1024 * 1024))),
    )
    cpu_seconds = timeout_seconds + 1
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def execute(code: str) -> str:
    tree = ast.parse(code, mode="exec")
    CodeValidator().visit(tree)

    output = LimitedWriter(OUTPUT_LIMIT)
    original_stdout, original_stderr = sys.stdout, sys.stderr
    safe_globals = {
        "__builtins__": SAFE_BUILTINS,
        "Decimal": decimal.Decimal,
        "Fraction": fractions.Fraction,
        "decimal": decimal,
        "fractions": fractions,
        "functools": functools,
        "itertools": itertools,
        "json": json,
        "math": math,
        "statistics": statistics,
    }

    try:
        sys.stdout = output
        sys.stderr = output
        final_expr = tree.body[-1] if tree.body and isinstance(tree.body[-1], ast.Expr) else None
        prefix = tree.body[:-1] if final_expr else tree.body
        if prefix:
            module = ast.Module(body=prefix, type_ignores=[])
            ast.fix_missing_locations(module)
            exec(compile(module, "<echo-sandbox>", "exec"), safe_globals, safe_globals)
        if final_expr:
            expression = ast.Expression(final_expr.value)
            ast.fix_missing_locations(expression)
            result = eval(compile(expression, "<echo-sandbox>", "eval"), safe_globals, safe_globals)
            if result is not None:
                print(repr(result))
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr

    return output.getvalue()


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: sandbox_runner.py CODE_FILE")
    apply_resource_limits()
    code = Path(sys.argv[1]).read_text(encoding="utf-8")
    try:
        result = execute(code)
    except BaseException as exc:  # 只向上层返回简短错误，不泄露堆栈与路径。
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    if result:
        print(result, end="")


if __name__ == "__main__":
    main()
