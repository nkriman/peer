"""Safe utility-formula parser for program.md.

The autoresearch loop computes a single scalar utility from each
iteration's metrics. The formula lives in program.md under a `## Utility`
section in a python-fenced block:

    ## Utility

    ```python
    score = detection_rate - 0.05 * max(0, n_comments_total / dataset_size - 5)
    ```

We do NOT exec arbitrary Python. We parse the expression on the RHS of
the assignment, AST-walk it, and only allow:

  - Number / Name / BinOp (+ - * / **) / UnaryOp (-) / Compare (no chains)
  - Name nodes restricted to a known metrics whitelist
  - Call nodes restricted to `max` and `min`

Anything else raises `UnsafeUtilityFormula`.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

from ..exceptions import PeerError

_ALLOWED_METRICS = {
    "detection_rate",
    "precision_minor",
    "precision_important",
    "precision_critical",
    "cost_usd",
    "cost_usd_total",
    "n_comments_total",
    "dataset_size",
    "suggestion_rate",
}
_ALLOWED_CALLS = {"max", "min"}


class UnsafeUtilityFormula(PeerError):
    """Raised when the utility formula contains constructs we don't allow."""


def default_utility(metrics: dict[str, float | int | None]) -> float:
    """Fallback when program.md is missing / unparseable.

    Returns detection_rate as the headline number, defaulting to 0.0 when
    the eval didn't compute one (e.g., all gold counts were 0).
    """
    v = metrics.get("detection_rate")
    return float(v) if v is not None else 0.0


def parse_utility_formula(
    program_md_text: str | None,
) -> Callable[[dict[str, float | int | None]], float]:
    """Return a callable that scores a metrics dict.

    `program_md_text=None` returns `default_utility`. Otherwise looks for
    the first ```python fenced block under `## Utility`, parses its
    `score = <expr>` line, and returns a validator+evaluator over <expr>.
    """
    if program_md_text is None:
        return default_utility
    expr = _extract_utility_expression(program_md_text)
    if expr is None:
        return default_utility
    tree = ast.parse(expr, mode="eval")
    _validate_node(tree.body)

    def _eval(metrics: dict[str, float | int | None]) -> float:
        return float(_eval_node(tree.body, metrics))

    return _eval


def _extract_utility_expression(text: str) -> str | None:
    """Extract `<rhs>` from a `score = <rhs>` line inside the first
    ```python fenced block under `## Utility`."""
    in_section = False
    in_fence = False
    fence_lines: list[str] = []
    for line in text.splitlines():
        if not in_section:
            if line.strip().lower().startswith("## utility"):
                in_section = True
            continue
        # In the section
        if not in_fence:
            if line.strip().startswith("```"):
                in_fence = True
            elif line.strip().startswith("## ") or line.strip().startswith("# "):
                # Section ended before any fenced block
                return None
            continue
        # In fence
        if line.strip().startswith("```"):
            break
        fence_lines.append(line)
    if not fence_lines:
        return None
    for raw in fence_lines:
        stripped = raw.strip()
        if stripped.startswith("score") and "=" in stripped:
            return stripped.split("=", 1)[1].strip()
    return None


def _validate_node(node: ast.AST) -> None:
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise UnsafeUtilityFormula(f"only numeric constants allowed; got {node.value!r}")
        return
    if isinstance(node, ast.Name):
        if node.id not in _ALLOWED_METRICS:
            raise UnsafeUtilityFormula(
                f"unknown metric name {node.id!r}; allowed: {sorted(_ALLOWED_METRICS)}"
            )
        return
    if isinstance(node, ast.BinOp):
        if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            raise UnsafeUtilityFormula(f"binop {type(node.op).__name__} not allowed")
        _validate_node(node.left)
        _validate_node(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, (ast.USub, ast.UAdd)):
            raise UnsafeUtilityFormula(f"unaryop {type(node.op).__name__} not allowed")
        _validate_node(node.operand)
        return
    if isinstance(node, ast.Call):
        if not (isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_CALLS):
            raise UnsafeUtilityFormula(
                f"only {sorted(_ALLOWED_CALLS)} calls allowed; got {ast.dump(node.func)}"
            )
        for arg in node.args:
            _validate_node(arg)
        if node.keywords:
            raise UnsafeUtilityFormula("keyword args not allowed in utility calls")
        return
    raise UnsafeUtilityFormula(f"AST node {type(node).__name__} not allowed in utility formula")


def _eval_node(node: ast.AST, metrics: dict[str, float | int | None]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        v = metrics.get(node.id)
        return 0 if v is None else v
    if isinstance(node, ast.BinOp):
        lhs = _eval_node(node.left, metrics)
        rhs = _eval_node(node.right, metrics)
        if isinstance(node.op, ast.Add):
            return lhs + rhs
        if isinstance(node.op, ast.Sub):
            return lhs - rhs
        if isinstance(node.op, ast.Mult):
            return lhs * rhs
        if isinstance(node.op, ast.Div):
            return lhs / rhs
        if isinstance(node.op, ast.Pow):
            return lhs**rhs
    if isinstance(node, ast.UnaryOp):
        v = _eval_node(node.operand, metrics)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.Call):
        assert isinstance(node.func, ast.Name)  # validated upstream
        func_name = node.func.id
        args = [_eval_node(a, metrics) for a in node.args]
        if func_name == "max":
            return max(*args)
        if func_name == "min":
            return min(*args)
    raise UnsafeUtilityFormula(f"unhandled AST node {type(node).__name__} during eval")
