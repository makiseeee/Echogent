"""AST 语法树白名单安全数学计算器 (SafeCalculator)。"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any


def _safe_pow(base: Any, exp: Any) -> Any:
    """带阈值上限的安全幂运算，防止超大指数引起 CPU 锁死与 OOM。"""
    if isinstance(exp, (int, float)):
        if abs(exp) > 1000:
            raise ValueError(f"指数过大 (上限 1000，当前为 {exp})")
        if isinstance(base, (int, float)) and abs(base) > 100 and abs(exp) > 100:
            raise ValueError("运算结果基数与指数均过大，超出计算安全阈值")
    try:
        res = operator.pow(base, exp)
        if isinstance(res, int) and res.bit_length() > 4096:
            raise ValueError("数值结果过大，超出安全计算上限 (4096 bits)")
        return res
    except OverflowError:
        raise ValueError("数值溢出，超出计算范围")


def _safe_factorial(n: Any) -> int:
    """带阈值上限的阶乘函数，防止超大基数耗尽内存。"""
    if not isinstance(n, int) or n < 0:
        raise ValueError("阶乘输入必须为非负整数")
    if n > 100:
        raise ValueError(f"阶乘基数过大 (上限 100，当前为 {n})")
    return math.factorial(n)


def _safe_exp(x: Any) -> float:
    """防止 exp 引起浮点溢出。"""
    if isinstance(x, (int, float)) and x > 700:
        raise ValueError("exp 指数过大 (上限 700)")
    return math.exp(x)


class SafeCalculator:
    """仅允许纯算术与基础数学函数的安全求值器，杜绝代码注入与 DoS 炸弹。"""

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
        "exp": _safe_exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pow": _safe_pow,
        "factorial": _safe_factorial,
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
        ast.Pow: _safe_pow,
    }

    @classmethod
    def safe_eval(cls, expr: str) -> int | float:
        """解析并计算数学表达式，不安全节点即刻抛出 ValueError。"""
        if len(expr) > 500:
            raise ValueError("表达式过长 (上限 500 字符)")
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
