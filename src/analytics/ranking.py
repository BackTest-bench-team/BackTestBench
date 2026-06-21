"""Top-N ranking helpers for Analytics MVP-1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Sequence

from src.engine.models import MetricsReport


@dataclass(frozen=True)
class TopNEntry:
    rank: int
    strategy_id: str
    instrument: str
    run_id: str
    total_pnl: float
    computed_at: datetime


def build_top_n(
    reports: Sequence[MetricsReport],
    *,
    run_ids: dict[tuple[str, str], str] | None = None,
    calculated_at: datetime | None = None,
    n: int = 10,
) -> list[TopNEntry]:
    """Filter reports above deposit baseline and rank them by total P&L."""

    if n <= 0:
        return []

    calculated_at = calculated_at or datetime.now(UTC)
    run_ids = run_ids or {}
    eligible = [r for r in reports if r.total_pnl > r.deposit_baseline_pnl]
    eligible.sort(key=lambda r: r.total_pnl, reverse=True)

    entries: list[TopNEntry] = []
    for rank, report in enumerate(eligible[:n], start=1):
        entries.append(
            TopNEntry(
                rank=rank,
                strategy_id=report.strategy_id,
                instrument=report.instrument,
                run_id=run_ids.get((report.strategy_id, report.instrument), ""),
                total_pnl=report.total_pnl,
                computed_at=calculated_at,
            )
        )
    return entries
