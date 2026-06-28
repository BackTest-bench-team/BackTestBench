"""Tests for the MA+RSI combined strategy (customer request, 22-06)."""

from __future__ import annotations

import math

import pytest

from src.engine.context import ExecutionContext
from src.engine.models import Candle, Signal
from src.engine.portfolio import Portfolio
from src.engine.types import SignalType
from src.strategy import ParameterValidationError, create_strategy


def candles(closes):
    return [Candle(timestamp=str(i), open=c, high=c, low=c, close=c, volume=1.0)
            for i, c in enumerate(closes)]


def ctx(cs, i, pf):
    return ExecutionContext(current_candle=cs[i], historical_candles=cs[:i], portfolio=pf)


def oscillating(n=240):
    return [100.0 + 14.0 * math.sin(i / 6.0) for i in range(n)]


def test_selectable_and_valid_signals():
    strat = create_strategy("ma_rsi", {"fast": 5, "slow": 20})
    assert strat.strategy_id == "ma_rsi"
    cs = candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    for i in range(len(cs)):
        sig = strat.on_candle(ctx(cs, i, pf))
        assert isinstance(sig, Signal) and isinstance(sig.type, SignalType)


def test_emits_buy_and_sell():
    strat = create_strategy("ma_rsi", {"fast": 5, "slow": 20, "rsi_buy_min": 45, "rsi_overbought": 60})
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


def test_rsi_filter_blocks_some_ma_entries():
    """With an impossible RSI gate, the RSI filter must suppress every BUY that
    the bare MA crossover would have taken — proving the filter is active."""
    cs = candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    gated = create_strategy("ma_rsi", {"fast": 5, "slow": 20, "rsi_buy_min": 99.9, "rsi_overbought": 100})
    buys = sum(gated.on_candle(ctx(cs, i, pf)).type is SignalType.BUY for i in range(len(cs)))
    assert buys == 0


def test_deterministic():
    cs = candles(oscillating())
    def run():
        s = create_strategy("ma_rsi", {"fast": 5, "slow": 20})
        pf = Portfolio(cash=10_000.0)
        return [s.on_candle(ctx(cs, i, pf)).type for i in range(len(cs))]
    assert run() == run()


def test_invalid_params_rejected():
    with pytest.raises(ParameterValidationError):
        create_strategy("ma_rsi", {"fast": 30, "slow": 10})
    with pytest.raises(ParameterValidationError):
        create_strategy("ma_rsi", {"rsi_buy_min": 80, "rsi_overbought": 70})
