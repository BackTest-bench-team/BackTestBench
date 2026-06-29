"""Validation metrics support for second-stage strategy evaluation.

Validation runs use the same metric formulas as historical backtests, but their
outputs are represented separately so they do not overwrite backtest results.
The current project has no durable database persistence, so this module provides
a small in-memory store with explicit backtest/validation buckets.  The store is
simple by design and can be replaced by the future ``metrics`` / validation DB
tables without changing the metric formulas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Sequence

from src.engine.models import MetricsReport, RunContext, TradeLog

from .metrics import MetricsConfig, calculate_metrics_from_trade_log


@dataclass(frozen=True)
class ValidationMetricsReport:
    """Metrics computed from a validation trade log.

    ``metrics`` contains the same values as a historical backtest report.  The
    wrapper stores validation-specific identity separately so ranking review can
    compare backtest Top-N rows with their later validation performance.
    """

    validation_run_id: str
    strategy_id: str
    instrument: str
    metrics: MetricsReport
    source_backtest_run_id: str = ""
    computed_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AnalyticsResultStore:
    """In-memory analytics result store with separate backtest/validation buckets."""

    def __init__(self) -> None:
        self._backtest_metrics: dict[str, MetricsReport] = {}
        self._validation_metrics: dict[str, ValidationMetricsReport] = {}

    def save_backtest_metrics(self, run_id: str, metrics: MetricsReport) -> None:
        if not run_id:
            raise ValueError("run_id is required for backtest metrics")
        self._backtest_metrics[run_id] = metrics

    def save_validation_metrics(self, report: ValidationMetricsReport) -> None:
        if not report.validation_run_id:
            raise ValueError("validation_run_id is required for validation metrics")
        self._validation_metrics[report.validation_run_id] = report

    def list_backtest_metrics(self) -> list[MetricsReport]:
        return list(self._backtest_metrics.values())

    def list_validation_metrics(
        self,
        *,
        strategy_id: str | None = None,
        instrument: str | None = None,
    ) -> list[ValidationMetricsReport]:
        reports = list(self._validation_metrics.values())
        if strategy_id is not None:
            reports = [report for report in reports if report.strategy_id == strategy_id]
        if instrument is not None:
            reports = [report for report in reports if report.instrument == instrument]
        return reports

    def latest_validation_by_strategy(self) -> dict[tuple[str, str], ValidationMetricsReport]:
        latest: dict[tuple[str, str], ValidationMetricsReport] = {}
        for report in self._validation_metrics.values():
            key = (report.strategy_id, report.instrument)
            previous = latest.get(key)
            if previous is None or report.computed_at >= previous.computed_at:
                latest[key] = report
        return latest


def calculate_validation_metrics_from_trade_log(
    trade_log: TradeLog,
    context: RunContext,
    *,
    validation_run_id: str | None = None,
    source_backtest_run_id: str = "",
    computed_at: datetime | None = None,
    config: MetricsConfig | None = None,
) -> ValidationMetricsReport:
    """Calculate validation metrics by reusing the standard metric pipeline."""

    metrics = calculate_metrics_from_trade_log(trade_log, context, config=config)
    return ValidationMetricsReport(
        validation_run_id=validation_run_id or context.run_id,
        strategy_id=metrics.strategy_id,
        instrument=metrics.instrument,
        metrics=metrics,
        source_backtest_run_id=source_backtest_run_id,
        computed_at=computed_at or datetime.now(UTC),
    )


def validation_reports_for_ranking_review(
    reports: Sequence[ValidationMetricsReport],
) -> list[ValidationMetricsReport]:
    """Return latest validation result per strategy/instrument for ranking review."""

    store = AnalyticsResultStore()
    for report in reports:
        store.save_validation_metrics(report)
    return list(store.latest_validation_by_strategy().values())
