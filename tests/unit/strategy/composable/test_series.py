"""Series registry + DAG precompute."""

from __future__ import annotations

import pytest

from src.strategy.composable import precompute, series_fn_names, topological_order
from src.strategy.composable.series import SeriesNode, build_nodes, sma, ema, rsi, diff, shift


PRICES = [10, 11, 12, 11, 13, 14, 13, 15, 16, 15]


def test_p0_series_fns_registered():
    for name in ("sma", "ema", "rsi", "diff", "shift"):
        assert name in series_fn_names()


def test_sma_values():
    out = sma(PRICES, period=3)
    assert out[0] == 10                      # partial window
    assert out[2] == pytest.approx((10 + 11 + 12) / 3)
    assert out[4] == pytest.approx((12 + 11 + 13) / 3)
    assert len(out) == len(PRICES)


def test_ema_and_ops():
    e = ema(PRICES, period=3)
    assert e[0] == 10 and len(e) == len(PRICES)
    d = diff([3, 5, 7], [1, 2, 3])
    assert d == [2, 3, 4]
    assert shift([1, 2, 3, 4], n=1) == [1, 1, 2, 3]


def test_rsi_bounds():
    r = rsi(PRICES, period=3)
    assert len(r) == len(PRICES)
    assert all(0 <= x <= 100 for x in r)


def test_precompute_dag_order():
    cfg = {
        "fast": {"fn": "sma", "source": "price", "period": 3},
        "slow": {"fn": "sma", "source": "price", "period": 5},
        "spread": {"fn": "diff", "a": "fast", "b": "slow"},
    }
    nodes = build_nodes(cfg)
    order = [n.id for n in topological_order(nodes)]
    assert order.index("spread") > order.index("fast")  # deps first
    values = precompute(nodes, PRICES)
    assert set(values) == {"price", "fast", "slow", "spread"}
    assert values["spread"][-1] == pytest.approx(values["fast"][-1] - values["slow"][-1])


def test_cycle_detected():
    nodes = [
        SeriesNode("a", "diff", {"a": "b", "b": "price"}, {}),
        SeriesNode("b", "diff", {"a": "a", "b": "price"}, {}),
    ]
    with pytest.raises(Exception):
        topological_order(nodes)


def test_unknown_input_rejected():
    nodes = build_nodes({"x": {"fn": "sma", "source": "nope", "period": 3}})
    with pytest.raises(Exception):
        topological_order(nodes)
