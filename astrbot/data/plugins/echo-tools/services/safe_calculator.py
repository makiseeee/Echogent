"""AST 语法树白名单安全数学计算器 (SafeCalculator)。"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any


class SafeCalculator:
    """仅允许纯算术与基础数学函数的安全求值器，杜绝代码注入。"""

    ALLOWED_NAMES: dict[str, Any] = {
        "pi": math.pi,
        "e": math.e,
        "tau": math.tau,
        "inf": math.inf,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": math.pow,
        "factorial": math.factorial,
        "degrees": math.degrees,
        "radians": math.radians,
    }

    ALLOWED_NODES = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Constant,
        ast.Name,
        ast.Call,
        ast.Load,
        ast.Store,
        ast.Del,
        ast.keyword,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
    )

    OP_MAP = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }

    @classmethod
    def safe_eval(cls, expr: str) -> int | float:
        """解析并计算数学表达式，不安全节点即刻抛出 ValueError。"""
        cleaned = expr.replace("^", "**")
        tree = ast.parse(cleaned, mode="eval")

        for node in ast.walk(tree):
            if not isinstance(node, cls.ALLOWED_NODES):
                raise ValueError("表达式包含不支持的运算")
            if isinstance(node, ast.Name) and node.id not in cls.ALLOWED_NAMES:
                raise ValueError(f"不支持的函数或常量：{node.id}")
            if isinstance(node, ast.Call) and not isinstance(node.func, ast.Name):
                raise ValueError("不支持的调用")

        def _eval(node: ast.AST) -> Any:
            if isinstance(node, ast.Constant):
                return node.value
            if isinstance(node, ast.Name):
                return cls.ALLOWED_NAMES[node.id]
            if isinstance(node, ast.BinOp):
                return cls.OP_MAP[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.USub):
                    return -_eval(node.operand)
                if isinstance(node.op, ast.UAdd):
                    return +_eval(node.operand)
            if isinstance(node, ast.Call):
                func = cls.ALLOWED_NAMES[node.func.id]
                args = [_eval(a) for a in node.args]
                return func(*args)
            raise ValueError("不支持的表达式")

        result = _eval(tree.body)
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return result

    @classmethod
    def evaluate(cls, expression: str) -> str:
        """为 LLM 工具输出标准运算结果字符串。"""
        try:
            res = cls.safe_eval(expression)
            return f"{expression} = {res}"
        except Exception as exc:  # noqa: BLE001
            return f"计算失败：{exc}"
