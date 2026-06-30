"""Unified candle format for all broker adapters."""
from datetime import datetime, timezone

from src.engine.models import Candle


def normalize_candle(c: Candle) -> Candle:
    """Coerce adapter output to engine Candle: UTC naive ISO timestamp, float OHLCV."""
    ts = c.timestamp.replace("Z", "+00:00") if isinstance(c.timestamp, str) else c.timestamp
    dt = datetime.fromisoformat(ts) if isinstance(ts, str) else ts
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return Candle(
        timestamp=dt.strftime("%Y-%m-%dT%H:%M:%S"),
        open=float(c.open),
        high=float(c.high),
        low=float(c.low),
        close=float(c.close),
        volume=float(c.volume) if c.volume is not None else 0.0,
    )
