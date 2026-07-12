"""Tests for explore stability scoring."""

from src.stability import compute_explore_stability


def _points(strategy_values: list[float], benchmark_values: list[float] | None = None) -> list[dict]:
    bench = benchmark_values or strategy_values
    return [
        {
            "date": f"2026-01-{i + 1:02d}T00:00:00",
            "strategy_index": strategy_values[i],
            "benchmark_index": bench[i],
        }
        for i in range(len(strategy_values))
    ]


def test_stability_high_when_consistent_across_windows():
    strategy = [100, 102, 104, 106, 108, 110, 112, 114, 116, 118, 120, 122]
    benchmark = [100, 100.5, 101, 101.5, 102, 102.5, 103, 103.5, 104, 104.5, 105, 105.5]
    result = compute_explore_stability(_points(strategy, benchmark))
    assert result["stability"] is not None
    assert result["stability"] >= 70
    assert result["consistency_score"] == 100
    assert result["positive_windows"] == result["windows"]
    assert result["volatility"] is not None
    assert result["worst_period"] is not None


def test_stability_low_when_only_one_lucky_window():
    strategy = [100] * 11 + [130]
    benchmark = [100] * 12
    result = compute_explore_stability(_points(strategy, benchmark))
    assert result["stability"] is not None
    assert result["stability"] <= 45
    assert result["positive_windows"] == 1
    assert result["worst_period"] == 0.0


def test_stability_reports_volatility_and_worst_period():
    strategy = [100, 108, 102, 110, 104, 112, 106, 114]
    benchmark = [100, 101, 101, 102, 102, 103, 103, 104]
    result = compute_explore_stability(_points(strategy, benchmark), segment_count=2)
    assert result["volatility"] is not None
    assert result["worst_period"] is not None
    assert result["vs_benchmark"] is not None
    assert result["vs_benchmark"] > 0
