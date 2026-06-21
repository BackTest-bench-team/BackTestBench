""" Drives a YAML-configured strategy through the engine dev's real
``ExecutionEngine`` over a synthetic candle series and asserts the whole loop
works: config -> strategy -> on_candle(context) per candle -> BUY/SELL/HOLD
executed -> trade log produced. No stand-in engine — this uses ``engine`` as-is.
"""

from __future__ import annotations

import math

from src.engine import ExecutionEngine
from src.engine.models import Candle

from src.strategy import parse_config, create_from_config


def _candles(n: int = 200) -> list[Candle]:
    out = []
    for i in range(n):
        p = 100.0 + 12.0 * math.sin(i / 7.0)
        out.append(Candle(timestamp=str(i), open=p, high=p + 1, low=p - 1, close=p, volume=1000.0))
    return out


def test_end_to_end_backtest_with_real_engine():
    cfg = parse_config({
        "name": "ma_crossover",
        "instrument": "SBER",
        "timeframe": "1m",
        "params": {"fast": 5, "slow": 20, "order_size": 1.0},
    })
    strategy = create_from_config(cfg)

    result = ExecutionEngine().run(strategy, _candles(), initial_capital=10_000.0)

    # the engine produced completed trades and a valid final portfolio
    assert len(result["trade_log"]) >= 1
    assert result["final_portfolio"].equity > 0
    # each completed trade carries a P&L number
    for trade in result["trade_log"]:
        assert isinstance(trade.pnl, float)
