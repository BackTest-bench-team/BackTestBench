"""Core MVP-1 analytics metrics.

This module calculates the first version of the analytics pipeline from the
Simulation Engine output: closed trades plus a mark-to-market equity curve.

Implemented metrics:
* total P&L
* Sharpe ratio
* max drawdown
* win rate
* deposit baseline P&L

The functions are intentionally dependency-light and operate on plain dataclass
objects from ``src.engine.models`` so the analytics layer can be tested in
isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import sqrt
from typing import Iterable, Sequence

from src.engine.models import MetricsReport, RunContext, Trade, TradeLog

DEFAULT_ANNUAL_DEPOSIT_RATE = 0.13
DEFAULT_TRADING_DAYS_PER_YEAR = 252
DEFAULT_TRADING_HOURS_PER_DAY = 7


class DataIntegrityError(ValueError):
    """Raised when trade-log totals are inconsistent with portfolio value."""


@dataclass(frozen=True)
class MetricsConfig:
    """Configuration for metric calculations."""

    annual_deposit_rate: float = DEFAULT_ANNUAL_DEPOSIT_RATE
    risk_free_rate: float | None = 0.0
    periods_per_year: int | None = None
    trading_hours_per_day: int = DEFAULT_TRADING_HOURS_PER_DAY
    integrity_tolerance: float = 1e-6


def calculate_total_pnl(trades: Sequence[Trade]) -> float:
    """Return realized P&L as the sum of closed-trade P&L values."""

    return float(sum(trade.pnl for trade in trades))


def calculate_win_rate(trades: Sequence[Trade]) -> float:
    """Return fraction of profitable trades. Break-even trades are not wins."""

    if not trades:
        return 0.0
    wins = sum(1 for trade in trades if trade.pnl > 0)
    return float(wins / len(trades))


def calculate_profit_factor(trades: Sequence[Trade]) -> float:
    """Gross wins divided by gross losses. Returns 0 when there are no losses."""

    gross_wins = sum(float(trade.pnl) for trade in trades if trade.pnl > 0)
    gross_losses = abs(sum(float(trade.pnl) for trade in trades if trade.pnl < 0))
    if gross_losses <= 0:
        return float(gross_wins) if gross_wins > 0 else 0.0
    return float(gross_wins / gross_losses)


def calculate_total_return_pct(total_pnl: float, initial_capital: float) -> float:
    if initial_capital <= 0:
        return 0.0
    return float(total_pnl / initial_capital)


def calculate_calmar_ratio(
    total_return_pct: float,
    max_drawdown: float,
    *,
    period_start: datetime | str | None,
    period_end: datetime | str | None,
) -> float:
    """Annualized return divided by max drawdown (standard Calmar ratio)."""

    if max_drawdown <= 0 or period_start is None or period_end is None:
        return 0.0

    start = _to_datetime(period_start)
    end = _to_datetime(period_end)
    years = (end - start).total_seconds() / (365.25 * 24.0 * 60.0 * 60.0)
    if years <= 0:
        return 0.0

    final_multiple = 1.0 + total_return_pct
    if final_multiple <= 0:
        return 0.0

    annualized = final_multiple ** (1.0 / years) - 1.0
    return float(annualized / max_drawdown)


def _extract_strategy_index_series(
    chart_points: Sequence[dict[str, object] | object],
) -> list[float]:
    rows: list[tuple[str, float]] = []
    for point in chart_points:
        if isinstance(point, dict):
            date = point.get("date")
            index = point.get("strategy_index")
        else:
            date = getattr(point, "date", None)
            index = getattr(point, "strategy_index", None)
        if not date or index is None:
            continue
        rows.append((str(date), float(index)))
    rows.sort(key=lambda item: item[0])
    return [value for _, value in rows]


def calculate_period_consistency(
    chart_points: Sequence[dict[str, object] | object],
    *,
    periods: int = 4,
) -> tuple[float, int, int]:
    """Share of sub-periods where strategy index rose vs the previous sub-period.

    The lookback window is split into ``periods`` equal slices by bar count (not
    calendar months), so short intraday windows still produce a meaningful score.
    """

    values = _extract_strategy_index_series(chart_points)
    if len(values) < 2:
        return 0.0, 0, 0

    slice_count = max(2, int(periods))
    n = len(values)
    boundaries = [0]
    for i in range(1, slice_count):
        boundaries.append(i * n // slice_count)
    boundaries.append(n)

    segment_ends: list[float] = []
    for i in range(slice_count):
        start = boundaries[i]
        end = boundaries[i + 1]
        if start >= end:
            continue
        segment_ends.append(values[end - 1])

    if len(segment_ends) < 2:
        return 0.0, 0, len(segment_ends)

    positive = sum(
        1 for idx in range(1, len(segment_ends)) if segment_ends[idx] > segment_ends[idx - 1]
    )
    total = len(segment_ends) - 1
    return float(positive / total), positive, total


def calculate_monthly_consistency(
    chart_points: Sequence[dict[str, object] | object],
) -> tuple[float, int, int]:
    """Backward-compatible alias — consistency is now computed over four sub-periods."""

    return calculate_period_consistency(chart_points, periods=4)


def calculate_vs_buy_hold_pct(chart_points: Sequence[dict[str, object] | object]) -> float:
    points = [p for p in chart_points if p]
    if len(points) < 2:
        return 0.0

    first = points[0]
    last = points[-1]
    if isinstance(first, dict):
        strat_start = float(first.get("strategy_index") or 100.0)
        strat_end = float(last.get("strategy_index") or 100.0)
        bench_start = float(first.get("benchmark_index") or 100.0)
        bench_end = float(last.get("benchmark_index") or 100.0)
    else:
        strat_start = float(getattr(first, "strategy_index", 100.0))
        strat_end = float(getattr(last, "strategy_index", 100.0))
        bench_start = float(getattr(first, "benchmark_index", 100.0))
        bench_end = float(getattr(last, "benchmark_index", 100.0))

    if strat_start <= 0 or bench_start <= 0:
        return 0.0

    strat_return = (strat_end / strat_start) - 1.0
    bench_return = (bench_end / bench_start) - 1.0
    return float(strat_return - bench_return)


def calculate_max_drawdown(equity_curve: Sequence[float]) -> float:
    """Return largest peak-to-trough decline as a positive fraction."""

    if len(equity_curve) < 2:
        return 0.0

    peak = float(equity_curve[0])
    max_dd = 0.0

    for equity in equity_curve:
        equity = float(equity)
        if equity > peak:
            peak = equity
        if peak <= 0:
            continue
        drawdown = (peak - equity) / peak
        if drawdown > max_dd:
            max_dd = drawdown

    return float(max(0.0, max_dd))


def calculate_sharpe_ratio(
    equity_curve: Sequence[float],
    timeframe: str = "1d",
    *,
    risk_free_rate: float | None = 0.0,
    annual_deposit_rate: float = DEFAULT_ANNUAL_DEPOSIT_RATE,
    periods_per_year: int | None = None,
    trading_hours_per_day: int = DEFAULT_TRADING_HOURS_PER_DAY,
) -> float:
    """Return annualized Sharpe ratio based on simple equity returns.

    Neutral value ``0.0`` is returned for degenerate inputs and zero variance.
    By default MVP-1 uses ``risk_free_rate=0.0``. Passing ``None`` derives the
    per-period risk-free rate from ``annual_deposit_rate``.
    """

    if len(equity_curve) < 3:  # fewer than 2 returns -> sample std is undefined
        return 0.0

    periods = periods_per_year or periods_per_year_for_timeframe(
        timeframe,
        trading_hours_per_day=trading_hours_per_day,
    )
    if periods <= 0:
        return 0.0

    if risk_free_rate is None:
        risk_free_rate = (1.0 + annual_deposit_rate) ** (1.0 / periods) - 1.0

    returns: list[float] = []
    for prev, current in zip(equity_curve, equity_curve[1:]):
        prev = float(prev)
        current = float(current)
        if prev <= 0:
            continue
        returns.append((current - prev) / prev)

    n = len(returns)
    if n < 2:
        return 0.0

    excess_returns = [r - risk_free_rate for r in returns]
    mean_excess = sum(excess_returns) / n
    variance = sum((r - mean_excess) ** 2 for r in excess_returns) / (n - 1)
    std_excess = sqrt(variance)

    if std_excess == 0.0:
        return 0.0

    return float((mean_excess / std_excess) * sqrt(periods))


def calculate_deposit_baseline_pnl(
    initial_capital: float,
    period_start: datetime | str | None,
    period_end: datetime | str | None,
    *,
    annual_deposit_rate: float = DEFAULT_ANNUAL_DEPOSIT_RATE,
) -> float:
    """Return bank-deposit profit over the backtest window at ``annual_deposit_rate``.

    Uses compound interest from ``period_start`` to ``period_end`` (same window as P&L).
    Example: 100_000 RUB for ~1 year at 13% → about 13_000 RUB profit (final ≈ 113_000).
    """

    if period_start is None or period_end is None:
        return 0.0

    start = _to_datetime(period_start)
    end = _to_datetime(period_end)
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return 0.0

    years = seconds / (365.25 * 24.0 * 60.0 * 60.0)
    return float(initial_capital * ((1.0 + annual_deposit_rate) ** years - 1.0))


def calculate_metrics(
    trades: Sequence[Trade],
    *,
    equity_curve: Sequence[float] | None = None,
    initial_capital: float,
    timeframe: str = "1d",
    period_start: datetime | str | None = None,
    period_end: datetime | str | None = None,
    strategy_id: str = "",
    instrument: str = "",
    final_portfolio_value: float | None = None,
    chart_points: Sequence[dict[str, object] | object] | None = None,
    config: MetricsConfig | None = None,
) -> MetricsReport:
    """Calculate all MVP-1 metrics from a trade list and run context fields."""

    cfg = config or MetricsConfig()
    trades = list(trades)
    total_pnl = calculate_total_pnl(trades)

    if equity_curve is None:
        equity_curve = fallback_equity_curve(trades, initial_capital)
    else:
        equity_curve = [float(value) for value in equity_curve]

    if final_portfolio_value is not None:
        expected = float(final_portfolio_value) - float(initial_capital)
        if abs(total_pnl - expected) > cfg.integrity_tolerance:
            raise DataIntegrityError(
                "total_pnl does not match final_portfolio_value - initial_capital: "
                f"total_pnl={total_pnl}, expected={expected}"
            )

    max_drawdown = calculate_max_drawdown(equity_curve)
    total_return_pct = calculate_total_return_pct(total_pnl, initial_capital)
    points = chart_points or []
    consistency_pct, positive_months, total_months = calculate_period_consistency(points, periods=4)

    return MetricsReport(
        strategy_id=strategy_id,
        instrument=instrument,
        total_pnl=total_pnl,
        sharpe_ratio=calculate_sharpe_ratio(
            equity_curve,
            timeframe,
            risk_free_rate=cfg.risk_free_rate,
            annual_deposit_rate=cfg.annual_deposit_rate,
            periods_per_year=cfg.periods_per_year,
            trading_hours_per_day=cfg.trading_hours_per_day,
        ),
        max_drawdown=max_drawdown,
        win_rate=calculate_win_rate(trades),
        deposit_baseline_pnl=calculate_deposit_baseline_pnl(
            initial_capital,
            period_start,
            period_end,
            annual_deposit_rate=cfg.annual_deposit_rate,
        ),
        profit_factor=calculate_profit_factor(trades),
        calmar_ratio=calculate_calmar_ratio(
            total_return_pct,
            max_drawdown,
            period_start=period_start,
            period_end=period_end,
        ),
        consistency_pct=consistency_pct,
        total_return_pct=total_return_pct,
        vs_buy_hold_pct=calculate_vs_buy_hold_pct(points),
        positive_months=positive_months,
        total_months=total_months,
    )


def calculate_metrics_from_trade_log(
    trade_log: TradeLog,
    context: RunContext,
    *,
    chart_points: Sequence[dict[str, object] | object] | None = None,
    config: MetricsConfig | None = None,
) -> MetricsReport:
    """Calculate ``MetricsReport`` from the canonical TradeLog + RunContext."""

    return calculate_metrics(
        trade_log.trades,
        equity_curve=trade_log.equity_curve,
        initial_capital=context.initial_capital,
        timeframe=context.timeframe,
        period_start=context.period_start,
        period_end=context.period_end,
        strategy_id=context.strategy_id or trade_log.strategy_id,
        instrument=context.instrument or trade_log.instrument,
        final_portfolio_value=trade_log.final_portfolio_value,
        chart_points=chart_points,
        config=config,
    )


def metrics_to_dashboard_dict(metrics: MetricsReport) -> dict[str, float | int]:
    """Serialize metrics for the runtime dashboard JSON."""

    return {
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


def fallback_equity_curve(trades: Sequence[Trade], initial_capital: float) -> list[float]:
    """Build a realized-only fallback curve from closed trades."""

    curve = [float(initial_capital)]
    equity = float(initial_capital)
    for trade in trades:
        equity += float(trade.pnl)
        curve.append(equity)
    return curve


def periods_per_year_for_timeframe(
    timeframe: str,
    *,
    trading_hours_per_day: int = DEFAULT_TRADING_HOURS_PER_DAY,
) -> int:
    """Return default annualization periods for a supported candle timeframe."""

    mapping = {
        "1d": DEFAULT_TRADING_DAYS_PER_YEAR,
        "1h": DEFAULT_TRADING_DAYS_PER_YEAR * trading_hours_per_day,
        "1m": DEFAULT_TRADING_DAYS_PER_YEAR * trading_hours_per_day * 60,
    }
    return mapping.get(timeframe, DEFAULT_TRADING_DAYS_PER_YEAR)


def _to_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S")
