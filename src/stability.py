"""Explore stability analytics from time-sliced equity curves."""

from __future__ import annotations

import statistics
from typing import Any


def _segment_return(start_index: float, end_index: float) -> float:
    if start_index <= 0:
        return 0.0
    return (end_index / start_index) - 1.0


def _window_segments(
    chart_points: list[dict[str, Any]],
    *,
    segment_count: int = 4,
) -> tuple[list[float], list[float], int, int, float, float] | None:
    points = [p for p in chart_points if p.get("date")]
    if len(points) < 4:
        return None

    windows = min(segment_count, max(2, len(points) // 3))
    chunk = max(len(points) // windows, 2)
    segments: list[tuple[float, float, float, float]] = []

    for start_idx in range(0, len(points), chunk):
        end_idx = min(start_idx + chunk, len(points)) - 1
        if end_idx <= start_idx:
            continue
        first = points[start_idx]
        last = points[end_idx]
        segments.append(
            (
                float(first.get("strategy_index") or 100.0),
                float(last.get("strategy_index") or 100.0),
                float(first.get("benchmark_index") or 100.0),
                float(last.get("benchmark_index") or 100.0),
            )
        )
        if len(segments) >= windows:
            break

    if not segments:
        return None

    window_returns: list[float] = []
    benchmark_returns: list[float] = []
    positive_windows = 0
    beats_benchmark_windows = 0

    for strat_start, strat_end, bench_start, bench_end in segments:
        seg_ret = _segment_return(strat_start, strat_end)
        bench_ret = _segment_return(bench_start, bench_end)
        window_returns.append(seg_ret)
        benchmark_returns.append(bench_ret)
        if seg_ret > 0:
            positive_windows += 1
        if seg_ret > bench_ret:
            beats_benchmark_windows += 1

    total_strat_return = _segment_return(
        float(points[0].get("strategy_index") or 100.0),
        float(points[-1].get("strategy_index") or 100.0),
    )
    total_bench_return = _segment_return(
        float(points[0].get("benchmark_index") or 100.0),
        float(points[-1].get("benchmark_index") or 100.0),
    )
    vs_benchmark = total_strat_return - total_bench_return
    return window_returns, benchmark_returns, positive_windows, beats_benchmark_windows, vs_benchmark, total_strat_return


def compute_explore_stability(
    chart_points: list[dict[str, Any]],
    *,
    segment_count: int = 4,
) -> dict[str, Any]:
    """Compute explore stability metrics from equal time windows in one run."""
    empty = {
        "stability": None,
        "consistency_score": None,
        "worst_period": None,
        "volatility": None,
        "windows": 0,
        "positive_windows": 0,
        "beats_benchmark_windows": 0,
        "vs_benchmark": None,
        "note": "Not enough data points for window analysis",
    }

    parsed = _window_segments(chart_points, segment_count=segment_count)
    if parsed is None:
        return empty

    window_returns, _benchmark_returns, positive_windows, beats_benchmark_windows, vs_benchmark, total_strat_return = parsed
    window_count = len(window_returns)
    positive_ratio = positive_windows / window_count
    consistency_score = round(100 * positive_ratio)

    worst_period = min(window_returns)
    volatility = (
        statistics.pstdev(window_returns)
        if len(window_returns) > 1
        else abs(window_returns[0]) if window_returns else 0.0
    )

    volatility_component = max(0.0, 1.0 - volatility / 0.12)
    worst_component = max(0.0, 1.0 - max(0.0, -worst_period) / 0.08)
    stability = round(
        100
        * (
            0.40 * (consistency_score / 100.0)
            + 0.30 * volatility_component
            + 0.30 * worst_component
        )
    )

    if total_strat_return <= 0:
        stability = min(stability, round(100 * 0.5 * (positive_ratio + beats_benchmark_windows / window_count)))

    if window_count >= 3 and positive_windows == 1 and total_strat_return > 0:
        stability = min(stability, 40)

    positive_gains = [max(0.0, value) for value in window_returns]
    total_gain = sum(positive_gains)
    if window_count >= 3 and total_gain > 0:
        luck_share = max(positive_gains) / total_gain
        if luck_share > 0.85:
            stability = min(stability, round(50 * (1.0 - (luck_share - 0.85) / 0.15)))

    return {
        "stability": max(0, min(100, stability)),
        "consistency_score": consistency_score,
        "worst_period": round(worst_period, 4),
        "volatility": round(volatility, 4),
        "windows": window_count,
        "positive_windows": positive_windows,
        "beats_benchmark_windows": beats_benchmark_windows,
        "vs_benchmark": round(vs_benchmark, 4),
        "note": None,
    }


# Backward-compatible alias used while callers migrate.
compute_explore_robustness = compute_explore_stability
