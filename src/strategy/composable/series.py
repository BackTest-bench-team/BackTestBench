"""Series registry and DAG precompute.

A *Series* is one value per bar — an array over the timeline. Series are built
from ``price`` or from other series, forming a dependency graph (DAG). This
module holds:

  * ``@register_series_fn`` — the registry indicator and op functions plug into.
  * the built-in functions ``sma``, ``ema``, ``rsi`` (indicators) and ``diff``,
    ``shift`` (generic ops). ``price`` is the base series (the closing prices).
  * ``topological_order`` — orders nodes so each series is computed after the
    ones it depends on (and raises on cycles or unknown inputs).
  * ``precompute`` — computes every series array once for a price history. A
    parameter sweep can reuse these arrays across runs, which is why it is a
    single reusable function rather than inline per-bar work. """

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .errors import CompileError

FloatSeries = list[float]

# name -> (fn, input_keys)  where input_keys are the config keys holding series ids
_SERIES_FNS: dict[str, tuple[Callable, tuple[str, ...]]] = {}


def register_series_fn(name: str, inputs: tuple[str, ...] = ("source",)):
    """Register a series function. ``inputs`` names the config keys that carry
    upstream series ids (e.g. ("source",) for sma, ("a", "b") for diff)."""

    def deco(fn: Callable) -> Callable:
        if name in _SERIES_FNS:
            raise ValueError(f"series fn '{name}' already registered")
        _SERIES_FNS[name] = (fn, inputs)
        return fn

    return deco


def series_fn_names() -> list[str]:
    return sorted(_SERIES_FNS)


@dataclass
class SeriesNode:
    id: str
    fn: str
    inputs: dict[str, str]           # config key -> upstream series id
    params: dict = field(default_factory=dict)  # scalar params (period, n, ...)


# --------------------------------------------------------------------------- #
# built-in series functions
# --------------------------------------------------------------------------- #
@register_series_fn("sma")
def sma(source: FloatSeries, period: int) -> FloatSeries:
    out, running = [], 0.0
    from collections import deque
    window: deque[float] = deque(maxlen=period)
    for x in source:
        if len(window) == period:
            running -= window[0]
        window.append(x)
        running += x
        out.append(running / len(window))
    return out


@register_series_fn("ema")
def ema(source: FloatSeries, period: int) -> FloatSeries:
    if not source:
        return []
    alpha = 2.0 / (period + 1)
    out = [source[0]]
    for x in source[1:]:
        out.append(alpha * x + (1 - alpha) * out[-1])
    return out


@register_series_fn("rsi")
def rsi(source: FloatSeries, period: int) -> FloatSeries:
    out = [50.0]
    for i in range(1, len(source)):
        lo = max(1, i - period + 1)
        gains = losses = 0.0
        for k in range(lo, i + 1):
            d = source[k] - source[k - 1]
            if d >= 0:
                gains += d
            else:
                losses -= d
        avg_gain, avg_loss = gains / period, losses / period
        if avg_loss == 0:
            out.append(100.0 if avg_gain > 0 else 50.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100.0 - 100.0 / (1.0 + rs))
    return out


@register_series_fn("diff", inputs=("a", "b"))
def diff(a: FloatSeries, b: FloatSeries) -> FloatSeries:
    return [x - y for x, y in zip(a, b)]


@register_series_fn("shift")
def shift(source: FloatSeries, n: int = 1) -> FloatSeries:
    return [source[max(0, i - n)] for i in range(len(source))]


# --------------------------------------------------------------------------- #
# DAG build + precompute
# --------------------------------------------------------------------------- #
def build_nodes(series_config: dict) -> list[SeriesNode]:
    nodes: list[SeriesNode] = []
    for sid, spec in series_config.items():
        if not isinstance(spec, dict) or "fn" not in spec:
            raise CompileError(f"series '{sid}' must be a mapping with an 'fn'")
        fn = spec["fn"]
        if fn not in _SERIES_FNS:
            raise CompileError(
                f"series '{sid}' uses unknown fn '{fn}'; known: {series_fn_names()}"
            )
        _, input_keys = _SERIES_FNS[fn]
        inputs = {k: spec[k] for k in input_keys if k in spec}
        if len(inputs) != len(input_keys):
            missing = [k for k in input_keys if k not in spec]
            raise CompileError(f"series '{sid}' ({fn}) missing input(s): {missing}")
        params = {k: v for k, v in spec.items() if k not in ("fn", *input_keys)}
        nodes.append(SeriesNode(sid, fn, inputs, params))
    return nodes


def topological_order(nodes: list[SeriesNode]) -> list[SeriesNode]:
    by_id = {n.id: n for n in nodes}
    if len(by_id) != len(nodes):
        raise CompileError("duplicate series id")
    ordered: list[SeriesNode] = []
    state: dict[str, int] = {}  # 0=unseen,1=visiting,2=done

    def visit(nid: str):
        if nid == "price":
            return
        if nid not in by_id:
            raise CompileError(f"series input '{nid}' is not defined (and is not 'price')")
        st = state.get(nid, 0)
        if st == 2:
            return
        if st == 1:
            raise CompileError(f"cycle detected in series DAG at '{nid}'")
        state[nid] = 1
        for up in by_id[nid].inputs.values():
            visit(up)
        state[nid] = 2
        ordered.append(by_id[nid])

    for n in nodes:
        visit(n.id)
    return ordered


def precompute(nodes: list[SeriesNode], prices: FloatSeries) -> dict[str, FloatSeries]:
    """Compute every series array once. Returns id -> array, incl. 'price'.

    Reused by ComposableStrategy per bar and — as the documented optimization
    hook — by the GridOptimizer across parameter combinations (the same nodes
    and prices yield the same arrays, so results can be cached by node identity).
    """
    ordered = topological_order(nodes)
    values: dict[str, FloatSeries] = {"price": list(prices)}
    for node in ordered:
        fn, input_keys = _SERIES_FNS[node.fn]
        args = [values[node.inputs[k]] for k in input_keys]
        values[node.id] = fn(*args, **node.params)
    return values
