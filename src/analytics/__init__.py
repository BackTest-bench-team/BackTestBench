"""Analytics Module public API."""

from .metrics import (
    DataIntegrityError,
    MetricsConfig,
    calculate_deposit_baseline_pnl,
    calculate_max_drawdown,
    calculate_metrics,
    calculate_metrics_from_trade_log,
    calculate_sharpe_ratio,
    calculate_total_pnl,
    calculate_win_rate,
    fallback_equity_curve,
    periods_per_year_for_timeframe,
)
from .optimizer import (
    OptimizerCandidate,
    OptimizerRankedEntry,
    build_optimizer_output,
    metrics_report_to_dict,
    optimizer_ranked_entry_to_dict,
    rank_optimizer_results,
)
from .ranking import RankingConfig, RankingReviewEntry, TopNEntry, build_ranking_review, build_top_n
from .validation import (
    AnalyticsResultStore,
    ValidationMetricsReport,
    calculate_validation_metrics_from_trade_log,
    validation_reports_for_ranking_review,
)

__all__ = [
    "DataIntegrityError",
    "MetricsConfig",
    "calculate_deposit_baseline_pnl",
    "calculate_max_drawdown",
    "calculate_metrics",
    "calculate_metrics_from_trade_log",
    "calculate_sharpe_ratio",
    "calculate_total_pnl",
    "calculate_win_rate",
    "fallback_equity_curve",
    "periods_per_year_for_timeframe",
    "OptimizerCandidate",
    "OptimizerRankedEntry",
    "build_optimizer_output",
    "metrics_report_to_dict",
    "optimizer_ranked_entry_to_dict",
    "rank_optimizer_results",
    "RankingConfig",
    "RankingReviewEntry",
    "TopNEntry",
    "build_ranking_review",
    "build_top_n",
    "AnalyticsResultStore",
    "ValidationMetricsReport",
    "calculate_validation_metrics_from_trade_log",
    "validation_reports_for_ranking_review",
]
