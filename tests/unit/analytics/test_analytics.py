from __future__ import annotations

from datetime import datetime
import math

import pytest

from src.analytics import (
    DataIntegrityError,
    MetricsConfig,
    build_top_n,
    calculate_max_drawdown,
    calculate_metrics,
    calculate_metrics_from_trade_log,
    calculate_sharpe_ratio,
    calculate_total_pnl,
    calculate_win_rate,
)
from src.engine.models import RunContext, Trade, TradeLog, MetricsReport


def trade(pnl: float) -> Trade:
    return Trade(
        timestamp="2025-01-02",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        quantity=1.0,
        pnl=pnl,
        opened_at="2025-01-01",
        closed_at="2025-01-02",
    )


def test_total_pnl_calculation_works():
    assert calculate_total_pnl([trade(10.0), trade(-3.5), trade(0.5)]) == 7.0
    assert calculate_total_pnl([]) == 0.0


def test_win_rate_calculation_works():
    assert calculate_win_rate([trade(10.0), trade(-3.5), trade(0.0), trade(2.0)]) == 0.5
    assert calculate_win_rate([]) == 0.0


def test_max_drawdown_calculation_works():
    equity = [1000.0, 1100.0, 990.0, 1200.0, 900.0, 950.0]
    assert calculate_max_drawdown(equity) == pytest.approx(0.25)
    assert calculate_max_drawdown([1000.0, 1100.0, 1200.0]) == 0.0
    assert calculate_max_drawdown([1000.0]) == 0.0


def test_sharpe_ratio_calculation_works():
    equity = [1000.0, 1010.0, 1005.0, 1030.0, 1020.0]
    returns = [(b - a) / a for a, b in zip(equity, equity[1:])]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    expected = (mean / math.sqrt(variance)) * math.sqrt(252)

    assert calculate_sharpe_ratio(equity, "1d") == pytest.approx(expected)
    assert calculate_sharpe_ratio([1000.0, 1000.0, 1000.0], "1d") == 0.0
    assert calculate_sharpe_ratio([1000.0, 1010.0], "1d") == 0.0


def test_calculate_metrics_from_trade_log_works():
    context = RunContext(
        run_id="run-1",
        strategy_id="ma_crossover",
        strategy_version="1",
        instrument="SBER",
        timeframe="1d",
        period_start=datetime(2025, 1, 1),
        period_end=datetime(2025, 2, 1),
        initial_capital=1000.0,
    )
    log = TradeLog(
        strategy_id="ma_crossover",
        instrument="SBER",
        trades=[trade(100.0), trade(-50.0)],
        final_portfolio_value=1050.0,
        equity_curve=[1000.0, 1100.0, 1040.0, 1050.0],
    )

    metrics = calculate_metrics_from_trade_log(log, context)

    assert metrics.strategy_id == "ma_crossover"
    assert metrics.instrument == "SBER"
    assert metrics.total_pnl == 50.0
    assert metrics.win_rate == 0.5
    assert metrics.max_drawdown == pytest.approx(60.0 / 1100.0)
    assert metrics.deposit_baseline_pnl > 0.0


def test_metrics_neutral_values_for_empty_inputs():
    metrics = calculate_metrics(
        [],
        equity_curve=[1000.0],
        initial_capital=1000.0,
        timeframe="1d",
        strategy_id="empty",
        instrument="SBER",
        final_portfolio_value=1000.0,
    )

    assert metrics.total_pnl == 0.0
    assert metrics.win_rate == 0.0
    assert metrics.max_drawdown == 0.0
    assert metrics.sharpe_ratio == 0.0


def test_data_integrity_error_when_totals_do_not_match_final_value():
    with pytest.raises(DataIntegrityError):
        calculate_metrics(
            [trade(10.0)],
            equity_curve=[1000.0, 1010.0],
            initial_capital=1000.0,
            final_portfolio_value=1200.0,
        )


def test_top_n_filters_baseline_and_sorts():
    reports = [
        MetricsReport("s1", "SBER", total_pnl=100.0, sharpe_ratio=1.0, max_drawdown=0.1, win_rate=0.5, deposit_baseline_pnl=50.0),
        MetricsReport("s2", "SBER", total_pnl=40.0, sharpe_ratio=2.0, max_drawdown=0.1, win_rate=0.7, deposit_baseline_pnl=50.0),
        MetricsReport("s3", "SBER", total_pnl=120.0, sharpe_ratio=1.5, max_drawdown=0.2, win_rate=0.6, deposit_baseline_pnl=50.0),
    ]

    top = build_top_n(reports, n=2)

    assert [entry.strategy_id for entry in top] == ["s3", "s1"]
    assert [entry.rank for entry in top] == [1, 2]
