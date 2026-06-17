"""Safe arithmetic evaluator — zero eval(), zero exec()."""
import ast
import operator as op
from typing import Union

_OPS = {
    ast.Add:      op.add,
    ast.Sub:      op.sub,
    ast.Mult:     op.mul,
    ast.Div:      op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod:      op.mod,
    ast.Pow:      op.pow,
    ast.USub:     op.neg,
    ast.UAdd:     op.pos,
}

_MAX_POWER = 1_000  # guard against 2**99999 DoS


def _eval(node: ast.expr) -> Union[int, float]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("only numeric literals allowed")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPS:
            raise ValueError(f"unsupported operator: {op_type.__name__}")
        left = _eval(node.left)
        right = _eval(node.right)
        if op_type is ast.Pow and abs(right) > _MAX_POWER:
            raise ValueError("exponent too large")
        return _OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPS:
            raise ValueError(f"unsupported unary op: {op_type.__name__}")
        return _OPS[op_type](_eval(node.operand))

    raise ValueError(f"unsupported node: {type(node).__name__}")


def safe_eval_math(expr: str) -> Union[int, float]:
    """
    Evaluate a math expression safely — no builtins, no attribute access,
    only +  -  *  /  //  %  ** and parentheses.

    Raises ValueError on any invalid or unsafe input.
    """
    expr = expr.strip().replace(",", ".")
    if not expr:
        raise ValueError("empty expression")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"invalid syntax: {exc}") from exc
    return _eval(tree.body)
