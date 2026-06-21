from dataclasses import dataclass
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