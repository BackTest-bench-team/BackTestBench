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
    """Return compound bank-deposit baseline P&L for the same period."""

    if period_start is None or period_end is None:
        return 0.0

    start = _to_datetime(period_start)
    end = _to_datetime(period_end)
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return 0.0

    years = seconds / (365.0 * 24.0 * 60.0 * 60.0)
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
        max_drawdown=calculate_max_drawdown(equity_curve),
        win_rate=calculate_win_rate(trades),
        deposit_baseline_pnl=calculate_deposit_baseline_pnl(
            initial_capital,
            period_start,
            period_end,
            annual_deposit_rate=cfg.annual_deposit_rate,
        ),
    )


def calculate_metrics_from_trade_log(
    trade_log: TradeLog,
    context: RunContext,
    *,
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
        config=config,
    )


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
    # Accept both plain ISO strings and common UTC ``Z`` suffix.
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
