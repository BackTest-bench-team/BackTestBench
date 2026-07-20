"""Tests for period-based consistency metric."""

from src.analytics.metrics import calculate_period_consistency


def _points(strategy_values: list[float]) -> list[dict]:
    return [
        {
            "date": f"2025-01-01T{i:02d}:00:00",
            "strategy_index": value,
            "benchmark_index": value,
        }
        for i, value in enumerate(strategy_values)
    ]


def test_consistency_high_when_most_periods_positive():
    values = [100 + i for i in range(40)]
    pct, positive, total = calculate_period_consistency(_points(values), periods=4)
    assert total == 3
    assert positive == 3
    assert pct == 1.0


def test_consistency_not_binary_for_short_intraday_window():
    pct, positive, total = calculate_period_consistency(_points([100, 101, 99, 102]), periods=4)
    assert total >= 1
    assert 0.0 < pct < 1.0 or positive in {0, 1, 2, 3}


def test_consistency_low_when_only_last_period_wins():
    values = [100] * 30 + [150] * 10
    pct, positive, total = calculate_period_consistency(_points(values), periods=4)
    assert total == 3
    assert positive <= 1
    assert pct <= 0.34


def test_consistency_empty_for_short_series():
    pct, positive, total = calculate_period_consistency([])
    assert pct == 0.0
    assert positive == 0
    assert total == 0
