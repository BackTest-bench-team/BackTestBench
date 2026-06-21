from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    type: str
    size: float = 1.0


@dataclass
class Trade:
    timestamp: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: float
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None


@dataclass
class TradeLog:
    strategy_id: str
    instrument: str
    trades: list[Trade] = field(default_factory=list)
    final_portfolio_value: float = 0.0
    equity_curve: list[float] = field(default_factory=list)


@dataclass
class RunContext:
    run_id: str
    strategy_id: str
    strategy_version: str
    instrument: str
    timeframe: str
    period_start: datetime | str
    period_end: datetime | str
    initial_capital: float


@dataclass
class MetricsReport:
    strategy_id: str
    instrument: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    deposit_baseline_pnl: float
