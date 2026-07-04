"""the per-bar evaluation context predicates and actions read from."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StrategyState:
    """Strategy-owned memory carried between bars."""
    bars_in_trade: int = 0
    last_action: str | None = None


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
