"""Validation rules for incoming candles."""
from typing import List

from src.engine.models import Candle

from .normalizer import normalize_candle


class ValidationError(Exception):
    pass


def prepare_candles(candles: List[Candle]) -> List[Candle]:
    """Filter invalid rows, fill missing volume, drop duplicate timestamps (last wins)."""
    by_ts: dict[str, Candle] = {}
    for c in candles:
        if any(v is None for v in (c.open, c.high, c.low, c.close)):
            continue
        if c.volume is not None and c.volume < 0:
            continue
        normalized = normalize_candle(c)
        by_ts[normalized.timestamp] = normalized
    return [by_ts[ts] for ts in sorted(by_ts)]


def validate_candles(candles: List[Candle]):
    """Checks before saving; raises when input is empty or nothing survives filtering."""
    if not candles:
        raise ValidationError("Candles list is empty")
    if not prepare_candles(candles):
        raise ValidationError("No valid candles after filtering")
