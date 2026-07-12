"""Predicate registry and the ``when``-block compiler.

A predicate returns true/false for the current bar. New conditions are added by
registering one function, so the compiler core never changes. ``compile_predicate``
turns a nested YAML ``when`` block into a single callable
``(EvaluationContext) -> bool``.

built-in predicates: gt, lt, gte, lte, cross_above, cross_below, all, any, not,
has_position, profit_pct, loss_pct."""

from __future__ import annotations

from typing import Callable

from .context import EvaluationContext
from .errors import CompileError

Predicate = Callable[[EvaluationContext], bool]

_PREDICATES: dict[str, Callable] = {}


def register_predicate(name: str):
    def deco(fn: Callable) -> Callable:
        if name in _PREDICATES:
            raise ValueError(f"predicate '{name}' already registered")
        _PREDICATES[name] = fn
        return fn

    return deco


def predicate_names() -> list[str]:
    return sorted(_PREDICATES)


# operand = number (constant) or series id (looked up at bar index)
def _resolve(operand, series_ids: set[str]):
    if isinstance(operand, bool):
        raise CompileError(f"operand may not be a bool: {operand!r}")
    if isinstance(operand, (int, float)):
        value = float(operand)
        return lambda ctx: value
    if isinstance(operand, str):
        if operand in series_ids or operand == "price":
            return lambda ctx: ctx.series[operand][ctx.index]
        raise CompileError(f"unknown series operand '{operand}'")
    raise CompileError(f"invalid operand: {operand!r}")


# ---- comparison predicates -------------------------------------------------
def _binary(op):
    def build(args, series_ids):
        if not (isinstance(args, list) and len(args) == 2):
            raise CompileError(f"comparison needs [a, b], got {args!r}")
        a, b = _resolve(args[0], series_ids), _resolve(args[1], series_ids)
        return lambda ctx: op(a(ctx), b(ctx))
    return build


register_predicate("gt")(_binary(lambda a, b: a > b))
register_predicate("lt")(_binary(lambda a, b: a < b))
register_predicate("gte")(_binary(lambda a, b: a >= b))
register_predicate("lte")(_binary(lambda a, b: a <= b))


def _cross(direction):
    def build(args, series_ids):
        if not (isinstance(args, list) and len(args) == 2):
            raise CompileError(f"{direction} needs [a, b], got {args!r}")
        aid, bid = args
        for sid in (aid, bid):
            if not (isinstance(sid, str) and (sid in series_ids or sid == "price")):
                raise CompileError(f"cross operand must be a series id, got {sid!r}")

        def pred(ctx: EvaluationContext) -> bool:
            i = ctx.index
            if i < 1:
                return False
            a, b = ctx.series[aid], ctx.series[bid]
            if direction == "above":
                return a[i - 1] <= b[i - 1] and a[i] > b[i]
            return a[i - 1] >= b[i - 1] and a[i] < b[i]

        return pred
    return build


register_predicate("cross_above")(_cross("above"))
register_predicate("cross_below")(_cross("below"))


@register_predicate("has_position")
def _has_position(arg, series_ids):
    want = bool(arg)
    return lambda ctx: ctx.is_long() == want


def _pct(kind):
    def build(arg, series_ids):
        # arg is a comparator dict, e.g. {gt: 5}
        if not (isinstance(arg, dict) and len(arg) == 1):
            raise CompileError(f"{kind} needs a comparator like {{gt: 5}}, got {arg!r}")
        (cmp_name, threshold), = arg.items()
        if cmp_name not in ("gt", "lt", "gte", "lte"):
            raise CompileError(f"{kind} comparator must be gt/lt/gte/lte, got '{cmp_name}'")
        thr = float(threshold)
        ops = {"gt": lambda v: v > thr, "lt": lambda v: v < thr,
               "gte": lambda v: v >= thr, "lte": lambda v: v <= thr}
        op = ops[cmp_name]
        getter = (lambda ctx: ctx.loss_pct()) if kind == "loss_pct" else (lambda ctx: ctx.profit_pct())
        return lambda ctx: ctx.is_long() and op(getter(ctx))
    return build


register_predicate("loss_pct")(_pct("loss_pct"))
register_predicate("profit_pct")(_pct("profit_pct"))


# ---- time-of-day / weekday predicates --------------------------------------
def _valid_hhmm(value) -> str:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        raise CompileError(f"time must be 'HH:MM', got {value!r}")
    hh, mm = value[:2], value[3:]
    if not (hh.isdigit() and mm.isdigit() and 0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise CompileError(f"time must be a valid 'HH:MM', got {value!r}")
    return value


@register_predicate("time_gte")
def _time_gte(arg, series_ids):
    target = _valid_hhmm(arg)
    return lambda ctx: (ctx.time_hhmm() or "") >= target


@register_predicate("time_lte")
def _time_lte(arg, series_ids):
    target = _valid_hhmm(arg)
    return lambda ctx: (t := ctx.time_hhmm()) is not None and t <= target


@register_predicate("time_in_range")
def _time_in_range(arg, series_ids):
    if not (isinstance(arg, list) and len(arg) == 2):
        raise CompileError(f"time_in_range needs ['HH:MM', 'HH:MM'], got {arg!r}")
    start, end = _valid_hhmm(arg[0]), _valid_hhmm(arg[1])

    def pred(ctx):
        t = ctx.time_hhmm()
        if t is None:
            return False
        return start <= t <= end if start <= end else (t >= start or t <= end)

    return pred


@register_predicate("weekday_in")
def _weekday_in(arg, series_ids):
    if not (isinstance(arg, list) and all(isinstance(d, int) and 0 <= d <= 6 for d in arg)):
        raise CompileError(f"weekday_in needs a list of 0..6 ints, got {arg!r}")
    days = set(arg)
    return lambda ctx: ctx.weekday() in days


# ---- trailing-stop breach --------------------------------------------------
@register_predicate("trailing_stop_hit")
def _trailing_stop_hit(arg, series_ids):
    want = bool(arg)
    def pred(ctx):
        level = ctx.state.trailing_stop_level
        hit = ctx.is_long() and level is not None and ctx.price <= level
        return hit == want
    return pred


# ---- account drawdown guard ------------------------------------------------
@register_predicate("equity_drawdown")
def _equity_drawdown(arg, series_ids):
    """True when equity is drawn down from its peak beyond a threshold.

    Lets a strategy stop opening new positions after a bad run, e.g.
    ``entry`` rule with ``when: { not: { equity_drawdown: { gte: 50 } } }``.
    """
    if not (isinstance(arg, dict) and len(arg) == 1):
        raise CompileError(f"equity_drawdown needs a comparator like {{gte: 50}}, got {arg!r}")
    (cmp_name, threshold), = arg.items()
    if cmp_name not in ("gt", "lt", "gte", "lte"):
        raise CompileError(f"equity_drawdown comparator must be gt/lt/gte/lte, got '{cmp_name}'")
    thr = float(threshold)
    ops = {"gt": lambda v: v > thr, "lt": lambda v: v < thr,
           "gte": lambda v: v >= thr, "lte": lambda v: v <= thr}
    op = ops[cmp_name]
    return lambda ctx: op(ctx.equity_drawdown_pct())


# ---- trend direction (a series rising / falling over a lookback) -----------
def _trend(direction):
    def build(arg, series_ids):
        # accept `rising: series` or `rising: [series, lookback]`
        if isinstance(arg, str):
            sid, lookback = arg, 1
        elif isinstance(arg, list) and len(arg) == 2:
            sid, lookback = arg[0], int(arg[1])
        else:
            raise CompileError(f"{direction} needs a series id or [series, lookback], got {arg!r}")
        if not (isinstance(sid, str) and (sid in series_ids or sid == "price")):
            raise CompileError(f"{direction} operand must be a series id, got {sid!r}")
        if lookback < 1:
            raise CompileError(f"{direction} lookback must be >= 1, got {lookback}")

        def pred(ctx):
            i = ctx.index
            if i < lookback:
                return False
            s = ctx.series[sid]
            return s[i] > s[i - lookback] if direction == "rising" else s[i] < s[i - lookback]

        return pred
    return build


register_predicate("rising")(_trend("rising"))
register_predicate("falling")(_trend("falling"))


# ---- combinators + compiler ------------------------------------------------
def compile_predicate(when: dict, series_ids: set[str]) -> Predicate:
    if not isinstance(when, dict) or len(when) != 1:
        raise CompileError(f"a condition must be a single-key mapping, got {when!r}")
    (key, val), = when.items()

    if key == "all":
        subs = [compile_predicate(w, series_ids) for w in val]
        return lambda ctx: all(p(ctx) for p in subs)
    if key == "any":
        subs = [compile_predicate(w, series_ids) for w in val]
        return lambda ctx: any(p(ctx) for p in subs)
    if key == "not":
        sub = compile_predicate(val, series_ids)
        return lambda ctx: not sub(ctx)

    if key not in _PREDICATES:
        raise CompileError(f"unknown predicate '{key}'; known: {predicate_names()}")
    return _PREDICATES[key](val, series_ids)
