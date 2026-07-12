"""Declarative cross-parameter constraints.

Strategies can declare relationships between parameters that must hold, e.g.
``fast < slow`` or ``take_profit_pct >= 2 * stop_loss_pct`` (a risk/reward
floor). These are checked once, at compile time, against the resolved parameter
values, so an invalid combination fails immediately with a clear message instead
of producing nonsense mid-backtest.

Grammar (one per line/list item):

    <term> <op> <term>

``<op>``   is one of  <  <=  >  >=  ==  !=
``<term>`` is a number, a parameter name, or a scaled parameter such as
           ``2 * stop_loss_pct`` (number * param, in either order).

The same ``check_constraints`` helper can be reused by non-composable strategies
that need the same cross-field validation."""

from __future__ import annotations

import operator
import re

from .errors import CompileError

_OPS = {
    "<=": operator.le, ">=": operator.ge, "==": operator.eq,
    "!=": operator.ne, "<": operator.lt, ">": operator.gt,
}
# longest operators first so "<=" isn't split as "<"
_OP_RE = re.compile(r"\s*(<=|>=|==|!=|<|>)\s*")


def _term_value(term: str, params: dict) -> float:
    term = term.strip()
    if "*" in term:
        parts = [p.strip() for p in term.split("*")]
        if len(parts) != 2:
            raise CompileError(f"invalid constraint term '{term}'")
        a, b = parts
        return _term_value(a, params) * _term_value(b, params)
    # number?
    try:
        return float(term)
    except ValueError:
        pass
    # parameter name?
    if term in params:
        value = params[term]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CompileError(f"constraint term '{term}' is not numeric")
        return float(value)
    raise CompileError(f"constraint refers to unknown parameter '{term}'")


def check_constraints(constraints: list[str], params: dict) -> None:
    """Raise CompileError if any constraint is violated by ``params``."""
    for raw in constraints:
        if not isinstance(raw, str):
            raise CompileError(f"each constraint must be a string, got {raw!r}")
        parts = _OP_RE.split(raw.strip())
        if len(parts) != 3:
            raise CompileError(
                f"constraint '{raw}' must look like 'a < b' (one comparison)"
            )
        lhs, op, rhs = parts
        if op not in _OPS:
            raise CompileError(f"constraint '{raw}' has invalid operator '{op}'")
        left, right = _term_value(lhs, params), _term_value(rhs, params)
        if not _OPS[op](left, right):
            raise CompileError(
                f"constraint not satisfied: {raw}  (with {lhs.strip()}={left:g}, "
                f"{rhs.strip()}={right:g})"
            )
