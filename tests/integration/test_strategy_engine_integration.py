"""End-to-end integration: strategy module <-> Simulation Engine (issue #68).

Drives YAML-configured strategies through the real ``ExecutionEngine`` candle by
candle and asserts the full loop works: config -> strategy -> on_candle(context)
per candle -> BUY/SELL/HOLD executed -> trade log. No stand-in engine.
"""

from __future__ import annotations

import math

import pytest

from src.engine import ExecutionEngine
from src.engine.models import Candle
from src.strategy import create_from_config, parse_config


def _candles(n: int = 200) -> list[Candle]:
    return [
        Candle(timestamp=str(i), open=(p := 100.0 + 12.0 * math.sin(i / 7.0)),
               high=p + 1, low=p - 1, close=p, volume=1000.0)
        for i in range(n)
    ]


@pytest.mark.parametrize("cfg_dict", [
    {"name": "ma_crossover", "instrument": "SBER", "params": {"fast": 5, "slow": 20}},
    {"name": "rsi_threshold", "instrument": "SBER", "params": {"period": 10, "oversold": 35, "overbought": 65}},
    {"name": "ma_rsi", "instrument": "SBER", "params": {"fast": 5, "slow": 20, "rsi_buy_min": 45, "rsi_overbought": 60}},
])
def test_end_to_end_backtest_with_real_engine(cfg_dict):
    candles = _candles()
    strategy = create_from_config(parse_config(cfg_dict))

    result = ExecutionEngine().run(strategy, candles, initial_capital=10_000.0)

    assert len(result["trade_log"]) >= 1
    assert result["final_portfolio"].equity > 0
    for trade in result["trade_log"]:
        assert isinstance(trade.pnl, float)
