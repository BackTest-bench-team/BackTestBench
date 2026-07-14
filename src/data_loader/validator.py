"""Validation rules for incoming candles."""
from typing import List

from src.engine.models import Candle

from .normalizer import normalize_candle


class ValidationError(Exception):
    pass


def _is_valid_ohlc(candle: Candle) -> bool:
    if any(value is None for value in (candle.open, candle.high, candle.low, candle.close)):
        return False
    if candle.volume is not None and candle.volume < 0:
        return False
    open_, high, low, close = (
        float(candle.open),
        float(candle.high),
        float(candle.low),
        float(candle.close),
    )
    if high < low:
        return False
    if high < max(open_, close) or low > min(open_, close):
        return False
    return True


def prepare_candles(candles: List[Candle]) -> List[Candle]:
    """Filter invalid rows, normalize timestamps/OHLCV, dedupe by timestamp (last wins)."""
    by_ts: dict[str, Candle] = {}
    for candle in candles:
        if not _is_valid_ohlc(candle):
            continue
        normalized = normalize_candle(candle)
        by_ts[normalized.timestamp] = normalized
    return [by_ts[ts] for ts in sorted(by_ts)]


def validate_candles(candles: List[Candle]) -> List[Candle]:
    """Validate and return cleaned candles ready for storage.

    Checked:
      - non-empty input
      - required OHLC fields present
      - non-negative volume (missing volume becomes 0 after normalize)
      - basic OHLC consistency (high >= low, high/low bracket open/close)
      - duplicate timestamps removed (last row wins)

    Not checked (deferred / out of scope for #120):
      - continuous time gaps or missing bars in the series
      - monotonic timestamps across the full history
      - cross-bar price jumps or corporate actions
      - instrument/timeframe correctness
      - incremental sync or train/validation dataset splits
    """
    if not candles:
        raise ValidationError("Candles list is empty")
    cleaned = prepare_candles(candles)
    if not cleaned:
        raise ValidationError("No valid candles after filtering")
    return cleaned
