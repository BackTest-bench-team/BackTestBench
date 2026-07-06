"""Lightweight market-data types exported by the Data Loader."""
from dataclasses import dataclass

from src.engine.models import Candle


@dataclass(frozen=True, slots=True)
class PriceBar:
    """Composable engine input: closing price at bar close time."""

    timestamp: str
    price: float


def price_bars_to_candles(bars: list[PriceBar]) -> list[Candle]:
    """Minimal Candle rows for ExecutionEngine when only (timestamp, price) is needed."""
    return [
        Candle(
            timestamp=bar.timestamp,
            open=bar.price,
            high=bar.price,
            low=bar.price,
            close=bar.price,
            volume=0.0,
        )
        for bar in bars
    ]
