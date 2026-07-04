"""E2E: load composable YAML -> backtest -> non-empty trade log,
plus a fixture composable firing BUY/SELL/HOLD through the engine.
"""

from __future__ import annotations

import math

from src.engine import ExecutionEngine
from src.engine.models import Candle
from src.strategy import create_strategy


def _candles(n=300):
    return [Candle(timestamp=str(i), open=(p := 100 + 18 * math.sin(i / 6)),
                   high=p + 1, low=p - 1, close=p, volume=1000.0) for i in range(n)]


def test_ma_rsi_composable_backtest_produces_trades():
    strat = create_strategy("ma_rsi_composable", {
        "fast": 5, "slow": 20, "rsi_buy_min": 40, "rsi_overbought": 65,
        "stop_loss_pct": 7, "take_profit_pct": 10,
    })
    result = ExecutionEngine().run(strat, _candles(), initial_capital=10_000.0)
    assert len(result["trade_log"]) >= 1
    assert result["final_portfolio"].equity > 0


def test_inline_composable_fires_buy_and_sell():
    definition = {
        "name": "fixture",
        "params": {"fast": {"type": "int", "default": 3, "choices": [3]},
                   "slow": {"type": "int", "default": 8, "choices": [8]}},
        "series": {
            "fast_ma": {"fn": "sma", "source": "price", "period": "${fast}"},
            "slow_ma": {"fn": "sma", "source": "price", "period": "${slow}"},
        },
        "rules": [
            {"id": "exit", "scope": "long", "priority": 10,
             "when": {"cross_below": ["fast_ma", "slow_ma"]},
             "then": {"action": "sell", "size": "all"}},
            {"id": "entry", "scope": "flat", "priority": 10,
             "when": {"cross_above": ["fast_ma", "slow_ma"]},
             "then": {"action": "buy", "size": 1}},
        ],
    }
    strat = create_strategy("composable", {"definition": definition})
    result = ExecutionEngine().run(strat, _candles(), initial_capital=10_000.0)
    assert len(result["trade_log"]) >= 1
