import math
from datetime import datetime, timedelta

import src.strategy.strategies  # noqa: F401 — register built-in strategies

from src.engine import ExecutionEngine
from src.engine.models import Candle, RunContext
from src.engine.optimization_engine import RandomSearchExecutionEngine, is_valid_param_combo
from src.strategy import discover_composable_strategies

discover_composable_strategies()


def _candles(n: int = 200) -> list[Candle]:
    base = datetime(2025, 1, 1, 10, 0, 0)
    return [
        Candle(
            timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            open=(price := 100 + 18 * math.sin(i / 6)),
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1000.0,
        )
        for i in range(n)
    ]


def _run(seed: int) -> dict:
    candles = _candles()
    context = RunContext(
        run_id="test",
        strategy_id="ma_rsi_composable",
        strategy_version="1",
        instrument="SBER",
        timeframe="1h",
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=100_000.0,
    )
    param_grid = {
        "fast": [10, 12, 21],
        "slow": [30, 50],
        "rsi_period": [14, 20],
        "rsi_buy_min": [40, 50],
        "rsi_overbought": [70],
        "stop_loss_pct": [0.5],
        "take_profit_pct": [1.0],
        "order_size": 1,
    }
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid=param_grid,
        candles=candles,
        initial_capital=100_000.0,
        run_context=context,
        n_iterations=8,
        target_metric="total_pnl",
        seed=seed,
        mode="sample",
    )
    assert result.best_metrics is not None
    return dict(result.best_params)


def test_invalid_fast_slow_combo_is_skipped():
    assert is_valid_param_combo({"fast": 30, "slow": 20}) is False
    assert is_valid_param_combo({"fast": 10, "slow": 30}) is True


def test_optimization_is_reproducible_with_same_seed():
    first = _run(seed=42)
    second = _run(seed=42)
    assert first == second


def test_optimization_differs_with_different_seed():
    first = _run(seed=42)
    second = _run(seed=99)
    assert first != second
