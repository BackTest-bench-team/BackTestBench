"""the per-bar evaluation context predicates and actions read from."""

from __future__ import annotations

from dataclasses import dataclass, field


from datetime import datetime


@dataclass
class StrategyState:
    """Strategy-owned memory carried between bars."""
    bars_in_trade: int = 0
    last_action: str | None = None
    was_long: bool = False
    peak_price: float | None = None          # highest price seen since entry
    trailing_stop_level: float | None = None  # current trailing-stop price
    peak_equity: float | None = None          # highest account equity seen so far


@dataclass
class EvaluationContext:
    """Everything predicates/actions can see at the current bar ``index``."""
    prices: list[float]
    series: dict[str, list[float]]          # id -> array (incl. "price")
    index: int
    timestamp: str
    portfolio: object                        # engine Portfolio (duck-typed)
    state: StrategyState = field(default_factory=StrategyState)

    @property
    def price(self) -> float:
        return self.prices[self.index]

    def is_long(self) -> bool:
        return getattr(self.portfolio, "position_size", 0) > 0

    def profit_pct(self) -> float:
        avg = getattr(self.portfolio, "average_entry_price", 0) or 0
        if not self.is_long() or avg <= 0:
            return 0.0
        return (self.price - avg) / avg * 100.0

    def loss_pct(self) -> float:
        return -self.profit_pct()

    def equity(self) -> float:
        """Account value now: cash plus the current worth of any open position.

        Computed here rather than read off the portfolio so it is correct at the
        moment the strategy runs (the engine only re-values the portfolio after
        the bar is processed)."""
        cash = getattr(self.portfolio, "cash", 0.0) or 0.0
        size = getattr(self.portfolio, "position_size", 0.0) or 0.0
        return cash + size * self.price

    def equity_drawdown_pct(self) -> float:
        """How far equity has fallen from its peak, in percent (0 if at a high)."""
        peak = self.state.peak_equity
        if not peak or peak <= 0:
            return 0.0
        return max(0.0, (peak - self.equity()) / peak * 100.0)

    def _dt(self) -> datetime | None:
        ts = self.timestamp
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M"):
                try:
                    return datetime.strptime(ts, fmt)
                except ValueError:
                    continue
        return None

    def time_hhmm(self) -> str | None:
        """Time-of-day as 'HH:MM', or None if the timestamp has no time part."""
        dt = self._dt()
        if dt is None:
            return None
        return dt.strftime("%H:%M")

    def weekday(self) -> int | None:
        """Weekday as 0=Mon .. 6=Sun, or None if unknown."""
        dt = self._dt()
        return None if dt is None else dt.weekday()
