"""Top-N ranking helpers for Analytics.

The ranking is intentionally kept in-memory because the current project does not
have durable metrics persistence yet.  The contract is stable enough for the
future Trading Bot / frontend consumers: callers pass already computed metrics,
this module filters invalid or below-baseline results, applies a documented sort
order, and returns a compact Top-N list.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any, Sequence

from src.engine.models import MetricsReport


@dataclass(frozen=True)
class RankingConfig:
    """Configuration for Top-N generation.

    Ranking criterion:
    1. include only reports with ``total_pnl > deposit_baseline_pnl``;
    2. sort by higher ``total_pnl``;
    3. if P&L ties, prefer lower ``max_drawdown``;
    4. then prefer higher ``sharpe_ratio``;
    5. then prefer higher ``win_rate``;
    6. then use ``strategy_id`` and ``instrument`` for deterministic ordering;
    7. exact duplicate keys keep their original input order.
    """

    n: int = 10
    require_above_baseline: bool = True


@dataclass(frozen=True)
class TopNEntry:
    rank: int
    strategy_id: str
    instrument: str
    run_id: str
    total_pnl: float
    computed_at: datetime
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    deposit_baseline_pnl: float = 0.0


@dataclass(frozen=True)
class RankingReviewEntry:
    """Top-N row enriched with optional validation metrics for review."""

    top_n: TopNEntry
    validation_metrics: MetricsReport | None = None
    validation_run_id: str = ""
    validation_computed_at: datetime | None = None


def build_top_n(
    reports: Sequence[MetricsReport | None],
    *,
    run_ids: dict[tuple[str, str], str] | None = None,
    calculated_at: datetime | None = None,
    n: int = 10,
    config: RankingConfig | None = None,
) -> list[TopNEntry]:
    """Generate a Top-N list from computed metrics.

    Empty input, ``None`` items, non-finite numeric values, and reports that do
    not beat the deposit baseline are handled by returning only valid eligible
    rows.  No exception is raised for partial input.
    """

    cfg = config or RankingConfig(n=n)
    limit = cfg.n if config is not None else n
    if limit <= 0:
        return []

    calculated_at = calculated_at or datetime.now(UTC)
    run_ids = run_ids or {}

    valid_reports = [
        (index, report)
        for index, report in enumerate(reports)
        if _is_valid_report(report)
    ]

    if cfg.require_above_baseline:
        valid_reports = [
            (index, report)
            for index, report in valid_reports
            if report.total_pnl > report.deposit_baseline_pnl
        ]

    # Python sorting is stable. The original index is the final key so exact
    # duplicate ranking keys preserve input order in a documented way.
    valid_reports.sort(key=lambda item: _ranking_key(item[1], item[0]))

    entries: list[TopNEntry] = []
    for rank, (_, report) in enumerate(valid_reports[:limit], start=1):
        entries.append(
            TopNEntry(
                rank=rank,
                strategy_id=report.strategy_id,
                instrument=report.instrument,
                run_id=run_ids.get((report.strategy_id, report.instrument), ""),
                total_pnl=float(report.total_pnl),
                computed_at=calculated_at,
                sharpe_ratio=float(report.sharpe_ratio),
                max_drawdown=float(report.max_drawdown),
                win_rate=float(report.win_rate),
                deposit_baseline_pnl=float(report.deposit_baseline_pnl),
            )
        )
    return entries


def build_ranking_review(
    top_n: Sequence[TopNEntry],
    validation_reports: Sequence[Any],
) -> list[RankingReviewEntry]:
    """Attach latest validation metrics to Top-N rows for ranking review.

    ``validation_reports`` are expected to be objects with ``strategy_id``,
    ``instrument``, ``metrics``, ``validation_run_id`` and ``computed_at``
    attributes.  This keeps the ranking module independent from the concrete
    validation storage implementation.
    """

    latest_validation: dict[tuple[str, str], Any] = {}
    for report in validation_reports:
        if report is None:
            continue
        key = (getattr(report, "strategy_id", ""), getattr(report, "instrument", ""))
        if not key[0] or not key[1]:
            continue
        previous = latest_validation.get(key)
        if previous is None or getattr(report, "computed_at", datetime.min) >= getattr(
            previous, "computed_at", datetime.min
        ):
            latest_validation[key] = report

    review: list[RankingReviewEntry] = []
    for entry in top_n:
        validation = latest_validation.get((entry.strategy_id, entry.instrument))
        review.append(
            RankingReviewEntry(
                top_n=entry,
                validation_metrics=getattr(validation, "metrics", None),
                validation_run_id=getattr(validation, "validation_run_id", ""),
                validation_computed_at=getattr(validation, "computed_at", None),
            )
        )
    return review


def _ranking_key(report: MetricsReport, original_index: int) -> tuple:
    return (
        -float(report.total_pnl),
        float(report.max_drawdown),
        -float(report.sharpe_ratio),
        -float(report.win_rate),
        str(report.strategy_id),
        str(report.instrument),
        original_index,
    )


def _is_valid_report(report: MetricsReport | None) -> bool:
    if report is None:
        return False
    numeric_values = (
        getattr(report, "total_pnl", None),
        getattr(report, "sharpe_ratio", None),
        getattr(report, "max_drawdown", None),
        getattr(report, "win_rate", None),
        getattr(report, "deposit_baseline_pnl", None),
    )
    try:
        return all(isfinite(float(value)) for value in numeric_values)
    except (TypeError, ValueError):
        return False
