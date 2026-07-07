import math
from datetime import datetime, timedelta

import src.strategy.strategies  # noqa: F401 — register built-in strategies

from src.engine import ExecutionEngine
from src.engine.models import Candle, RunContext
from src.engine.optimization_engine import RandomSearchExecutionEngine, is_valid_param_combo
from src.strategy import discover_composable_strategies

discover_composable_strategies()


def _candles(n: int = 200, *, flat: bool = False) -> list[Candle]:
    base = datetime(2025, 1, 1, 10, 0, 0)
    candles: list[Candle] = []
    for i in range(n):
        price = 100.0 if flat else 100 + 18 * math.sin(i / 6)
        candles.append(
            Candle(
                timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
                open=price,
                high=price + 1,
                low=price - 1,
                close=price,
                volume=1000.0,
            )
        )
    return candles


def _context(candles: list[Candle]) -> RunContext:
    return RunContext(
        run_id="test",
        strategy_id="ma_rsi_composable",
        strategy_version="1",
        instrument="SBER",
        timeframe="1h",
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=100_000.0,
    )


def _search_grid(**overrides):
    grid = {
        "fast": [10, 12, 21],
        "slow": [30, 50],
        "rsi_period": [14, 20],
        "rsi_buy_min": [40, 50],
        "rsi_overbought": [70],
        "stop_loss_pct": [0.5],
        "take_profit_pct": [1.0],
        "order_size": 1,
    }
    grid.update(overrides)
    return grid


def _run(seed: int, **grid_overrides) -> dict:
    candles = _candles()
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid=_search_grid(**grid_overrides),
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
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


def test_invalid_rsi_range_combo_is_rejected():
    assert is_valid_param_combo({"rsi_buy_min": 70, "rsi_overbought": 65}) is False
    assert is_valid_param_combo({"rsi_buy_min": 40, "rsi_overbought": 70}) is True


def test_optimization_is_reproducible_with_same_seed():
    first = _run(seed=42)
    second = _run(seed=42)
    assert first == second


def test_optimization_differs_with_different_seed():
    first = _run(seed=42)
    second = _run(seed=99)
    assert first != second


def test_fixed_params_only_runs_single_baseline():
    candles = _candles()
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid={
            "fast": 10,
            "slow": 30,
            "rsi_period": 14,
            "rsi_buy_min": 40,
            "rsi_overbought": 70,
            "stop_loss_pct": 0.5,
            "take_profit_pct": 1.0,
            "order_size": 1,
        },
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        mode="grid",
    )
    assert result.total_iterations_run == 1
    assert len(result.iterations) == 1
    assert result.best_params["fast"] == 10
    assert result.best_metrics is not None


def test_grid_mode_evaluates_all_combinations():
    candles = _candles()
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid={
            "fast": [10, 12],
            "slow": [30],
            "rsi_period": [14],
            "rsi_buy_min": [40],
            "rsi_overbought": [70],
            "stop_loss_pct": [0.5],
            "take_profit_pct": [1.0],
            "order_size": 1,
        },
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        mode="grid",
    )
    assert result.total_iterations_run == 2
    assert {it.params["fast"] for it in result.iterations} == {10, 12}


def test_should_stop_halts_optimization_early():
    candles = _candles()
    stop_after = {"count": 0}

    def should_stop() -> bool:
        stop_after["count"] += 1
        return stop_after["count"] >= 2

    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid=_search_grid(fast=[10, 12, 21], slow=[30, 50]),
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        mode="grid",
        should_stop=should_stop,
    )
    assert result.total_iterations_run <= 2


def test_optimization_returns_none_metrics_when_no_trades():
    candles = _candles(flat=True, n=80)
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid={
            "fast": [50],
            "slow": [100],
            "rsi_period": [14],
            "rsi_buy_min": [99],
            "rsi_overbought": [99],
            "stop_loss_pct": [0.5],
            "take_profit_pct": [1.0],
            "order_size": 1,
        },
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        mode="grid",
    )
    assert result.best_metrics is None
    assert result.total_iterations_run == 0
    assert result.best_trade_log_report.trades == []


def test_sample_mode_uses_all_combos_when_below_iteration_cap():
    candles = _candles()
    result = RandomSearchExecutionEngine(ExecutionEngine()).run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid={
            "fast": [10, 12],
            "slow": [30],
            "rsi_period": [14],
            "rsi_buy_min": [40],
            "rsi_overbought": [70],
            "stop_loss_pct": [0.5],
            "take_profit_pct": [1.0],
            "order_size": 1,
        },
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        n_iterations=100,
        mode="sample",
    )
    assert result.total_iterations_run == 2


def test_optimization_skips_failed_iterations(monkeypatch):
    candles = _candles()
    engine = RandomSearchExecutionEngine(ExecutionEngine())
    calls = {"count": 0}

    def boom_strategy(strategy_id, params):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("compile failed")
        from src.strategy import create_strategy as real_create
        return real_create(strategy_id, params)

    monkeypatch.setattr("src.engine.optimization_engine.create_strategy", boom_strategy)

    result = engine.run_optimization(
        strategy_id="ma_rsi_composable",
        param_grid={
            "fast": [10, 12],
            "slow": [30],
            "rsi_period": [14],
            "rsi_buy_min": [40],
            "rsi_overbought": [70],
            "stop_loss_pct": [0.5],
            "take_profit_pct": [1.0],
            "order_size": 1,
        },
        candles=candles,
        initial_capital=100_000.0,
        run_context=_context(candles),
        mode="grid",
    )
    assert result.total_iterations_run == 1
