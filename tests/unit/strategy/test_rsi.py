"""Tests for the second built-in strategy: RSI threshold (issue #67)."""

from __future__ import annotations

import math

import pytest

from src.engine.context import ExecutionContext
from src.engine.models import Candle, Signal
from src.engine.portfolio import Portfolio
from src.engine.types import SignalType
from src.strategy import ParameterValidationError, create_strategy, parse_config


def candles(closes):
    return [Candle(timestamp=str(i), open=c, high=c, low=c, close=c, volume=1.0)
            for i, c in enumerate(closes)]


def ctx(cs, i, pf):
    return ExecutionContext(current_candle=cs[i], historical_candles=cs[:i], portfolio=pf)


def oscillating(n=200):
    return [100.0 + 15.0 * math.sin(i / 5.0) for i in range(n)]


def test_selectable_from_config():
    strat = create_strategy("rsi_threshold", {"period": 10})
    assert strat.strategy_id == "rsi_threshold"


def test_returns_valid_signals_and_holds_during_warmup():
    strat = create_strategy("rsi_threshold", {"period": 14})
    cs = candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    for i in range(14):
        assert strat.on_candle(ctx(cs, i, pf)).type is SignalType.HOLD
    for i in range(len(cs)):
        sig = strat.on_candle(ctx(cs, i, pf))
        assert isinstance(sig, Signal) and isinstance(sig.type, SignalType)


def test_emits_buy_and_sell_on_oscillating_data():
    strat = create_strategy("rsi_threshold", {"period": 10, "oversold": 35, "overbought": 65})
    cs = candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    seen = set()
    for i in range(len(cs)):
        sig = strat.on_candle(ctx(cs, i, pf))
        seen.add(sig.type)
        if sig.type is SignalType.BUY:
            pf.position_size = 10.0
        elif sig.type is SignalType.SELL:
            pf.position_size = 0.0
    assert SignalType.BUY in seen and SignalType.SELL in seen


def test_deterministic_on_test_data():
    cs = candles(oscillating())
    def run():
        s = create_strategy("rsi_threshold", {"period": 10})
        pf = Portfolio(cash=10_000.0)
        return [s.on_candle(ctx(cs, i, pf)).type for i in range(len(cs))]
    assert run() == run()


def test_invalid_params_rejected():
    with pytest.raises(ParameterValidationError):
        create_strategy("rsi_threshold", {"oversold": 80, "overbought": 20})
    with pytest.raises(ParameterValidationError):
        create_strategy("rsi_threshold", {"period": 1})
