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
from .ranking import TopNEntry, build_top_n

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
    "TopNEntry",
    "build_top_n",
]
