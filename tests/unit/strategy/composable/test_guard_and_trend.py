"""Drawdown entry guard and trend-direction predicates."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.strategy.composable import EvaluationContext, compile_predicate
from src.strategy.composable.context import StrategyState


@dataclass
class FakePortfolio:
    cash: float = 10_000.0
    position_size: float = 0.0
    average_entry_price: float = 0.0


def ctx(price, state, series=None, prices=None, portfolio=None):
    prices = prices or [price]
    series = series or {"price": prices}
    return EvaluationContext(prices=prices, series=series, index=len(prices) - 1,
                             timestamp="t", portfolio=portfolio or FakePortfolio(), state=state)


# ---- equity drawdown guard -------------------------------------------------
def test_equity_drawdown_blocks_after_loss():
    state = StrategyState(peak_equity=10_000.0)
    pred = compile_predicate({"equity_drawdown": {"gte": 50}}, set())
    # equity now = cash 4000 -> 60% drawdown from 10k peak
    assert pred(ctx(1.0, state, portfolio=FakePortfolio(cash=4_000.0))) is True
    # equity now = 8000 -> 20% drawdown, below threshold
    assert pred(ctx(1.0, state, portfolio=FakePortfolio(cash=8_000.0))) is False


def test_equity_drawdown_zero_at_peak():
    state = StrategyState(peak_equity=10_000.0)
    pred = compile_predicate({"equity_drawdown": {"gt": 0}}, set())
    assert pred(ctx(1.0, state, portfolio=FakePortfolio(cash=10_000.0))) is False


def test_entry_guard_composition():
    # a realistic entry condition: signal AND not in deep drawdown
    state = StrategyState(peak_equity=10_000.0)
    pred = compile_predicate(
        {"all": [{"gt": ["price", 0]}, {"not": {"equity_drawdown": {"gte": 50}}}]},
        {"price"},
    )
    assert pred(ctx(1.0, state, portfolio=FakePortfolio(cash=9_000.0))) is True
    assert pred(ctx(1.0, state, portfolio=FakePortfolio(cash=3_000.0))) is False


# ---- trend direction -------------------------------------------------------
def test_rising_and_falling():
    series = {"trend": [10, 11, 12, 13, 14, 13, 12]}
    up = compile_predicate({"rising": ["trend", 3]}, {"trend"})
    down = compile_predicate({"falling": ["trend", 3]}, {"trend"})

    def at(i):
        return EvaluationContext(prices=series["trend"], series=series, index=i,
                                 timestamp="t", portfolio=FakePortfolio(), state=StrategyState())

    assert up(at(4)) is True     # 14 > 11 (index 4 vs 1)
    assert down(at(4)) is False
    assert down(at(6)) is True   # 12 < 13 (index 6 vs 3)
    assert up(at(6)) is False


def test_rising_default_lookback_and_warmup():
    series = {"ma": [5, 6, 7]}
    pred = compile_predicate({"rising": "ma"}, {"ma"})
    early = EvaluationContext(prices=[5], series={"ma": [5]}, index=0, timestamp="t",
                              portfolio=FakePortfolio(), state=StrategyState())
    assert pred(early) is False   # not enough history
    late = EvaluationContext(prices=[5, 6, 7], series=series, index=2, timestamp="t",
                             portfolio=FakePortfolio(), state=StrategyState())
    assert pred(late) is True     # 7 > 6


def test_bad_trend_arg_rejected():
    with pytest.raises(Exception):
        compile_predicate({"rising": ["ma", 0]}, {"ma"})
