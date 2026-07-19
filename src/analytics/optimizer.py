"""Optimizer result ranking helpers.

This module ranks parameter combinations produced by a grid/random optimizer for
one strategy. It is intentionally separate from ``build_top_n`` because Top-N
ranks different strategies, while optimizer ranking ranks parameter sets for the
same strategy after a search run.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

from src.engine.models import MetricsReport

from .ranking import RankingConfig


@dataclass(frozen=True)
class OptimizerCandidate:
    """Single optimizer attempt accepted by ``rank_optimizer_results``.

    ``trade_count`` is optional because existing callers often pass only
    ``(params, metrics)``. When it is provided and equals zero, the candidate is
    treated as an empty run and skipped.
    """

    params: Mapping[str, Any]
    metrics: MetricsReport | None
    trade_count: int | None = None


@dataclass(frozen=True)
class OptimizerRankedEntry:
    """Ranked optimizer row for one parameter combination."""

    rank: int
    params: dict[str, Any]
    metrics: MetricsReport


def rank_optimizer_results(
    reports: Sequence[
        tuple[Mapping[str, Any], MetricsReport | None]
        | tuple[Mapping[str, Any], MetricsReport | None, Any]
        | OptimizerCandidate
        | Mapping[str, Any]
        | None
    ],
    config: RankingConfig | None = None,
) -> list[OptimizerRankedEntry]:
    """Rank optimizer parameter combinations and return a stable ordered list.

    The input represents runs for one strategy. This is not a strategy catalogue
    Top-N and therefore does not call ``build_top_n``.

    Sort order reuses the analytics ranking convention: higher P&L, lower
    drawdown, higher Sharpe, higher win rate. Exact ties preserve the original
    input order because Python sorting is stable and the original index is kept
    as the final key.

    Invalid rows are skipped: ``None`` rows, missing/non-finite metrics, and
    candidates explicitly marked with ``trade_count == 0``.
    """

    cfg = config or RankingConfig()
    if cfg.n <= 0:
        return []

    candidates: list[tuple[int, OptimizerCandidate]] = []
    for index, item in enumerate(reports):
        candidate = _coerce_candidate(item)
        if candidate is None:
            continue
        if candidate.trade_count is not None and candidate.trade_count <= 0:
            continue
        if not _is_valid_metrics(candidate.metrics):
            continue
        candidates.append((index, candidate))

    candidates.sort(key=lambda item: _optimizer_ranking_key(item[1].metrics, item[0]))

    return [
        OptimizerRankedEntry(
            rank=rank,
            params=dict(candidate.params),
            metrics=candidate.metrics,  # type: ignore[arg-type]
        )
        for rank, (_, candidate) in enumerate(candidates[: cfg.n], start=1)
    ]


def build_optimizer_output(
    strategy_id: str,
    instrument: str,
    ranked: Sequence[OptimizerRankedEntry],
) -> dict[str, Any]:
    """Serialize optimizer ranking to the agreed dashboard/API schema."""

    return {
        "strategy_id": strategy_id,
        "instrument": instrument,
        "ranked": [optimizer_ranked_entry_to_dict(entry) for entry in ranked],
    }


def optimizer_ranked_entry_to_dict(entry: OptimizerRankedEntry) -> dict[str, Any]:
    """Serialize one optimizer row."""

    return {
        "rank": int(entry.rank),
        "params": dict(entry.params),
        "metrics": metrics_report_to_dict(entry.metrics),
    }


def metrics_report_to_dict(metrics: MetricsReport) -> dict[str, float | str]:
    """Serialize ``MetricsReport`` using JSON-friendly primitive values."""

    return {
        "strategy_id": metrics.strategy_id,
        "instrument": metrics.instrument,
        "total_pnl": float(metrics.total_pnl),
        "sharpe_ratio": float(metrics.sharpe_ratio),
        "max_drawdown": float(metrics.max_drawdown),
        "win_rate": float(metrics.win_rate),
        "deposit_baseline_pnl": float(metrics.deposit_baseline_pnl),
        "profit_factor": float(metrics.profit_factor),
        "calmar_ratio": float(metrics.calmar_ratio),
        "consistency_pct": float(metrics.consistency_pct),
        "total_return_pct": float(metrics.total_return_pct),
        "vs_buy_hold_pct": float(metrics.vs_buy_hold_pct),
        "positive_months": int(metrics.positive_months),
        "total_months": int(metrics.total_months),
    }


def _coerce_candidate(item: Any) -> OptimizerCandidate | None:
    if item is None:
        return None
    if isinstance(item, OptimizerCandidate):
        return item
    if isinstance(item, tuple):
        if len(item) == 2:
            params, metrics = item
            return OptimizerCandidate(params=params, metrics=metrics)
        if len(item) == 3:
            params, metrics, trade_source = item
            return OptimizerCandidate(
                params=params,
                metrics=metrics,
                trade_count=_trade_count_from(trade_source),
            )
        return None
    if isinstance(item, Mapping):
        params = item.get("params")
        metrics = item.get("metrics")
        if not isinstance(params, Mapping):
            return None
        return OptimizerCandidate(
            params=params,
            metrics=metrics,
            trade_count=_trade_count_from(
                item.get("trade_count", item.get("trade_log", item.get("trades")))
            ),
        )
    return None


def _trade_count_from(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if hasattr(value, "trades"):
        try:
            return len(value.trades)
        except TypeError:
            return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value)
    return None


def _optimizer_ranking_key(metrics: MetricsReport | None, original_index: int) -> tuple:
    assert metrics is not None
    return (
        -float(metrics.total_pnl),
        float(metrics.max_drawdown),
        -float(metrics.sharpe_ratio),
        -float(metrics.win_rate),
        original_index,
    )


def _is_valid_metrics(metrics: MetricsReport | None) -> bool:
    if metrics is None:
        return False
    values = (
        getattr(metrics, "total_pnl", None),
        getattr(metrics, "sharpe_ratio", None),
        getattr(metrics, "max_drawdown", None),
        getattr(metrics, "win_rate", None),
        getattr(metrics, "deposit_baseline_pnl", None),
    )
    try:
        return all(isfinite(float(value)) for value in values)
    except (TypeError, ValueError):
        return False
