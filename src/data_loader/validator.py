"""Validation rules for incoming candles."""
from typing import List
from src.engine.models import Candle

class ValidationError(Exception):
    pass

def validate_candles(candles: List[Candle]):
    """Checks before saving"""
    if not candles:
        raise ValidationError('Candles list is empty')
    for c in candles:
        if any(v is None for v in (c.open, c.high, c.low, c.close)):
            raise ValidationError(f'None price in candle {c.timestamp}')
        if c.volume is None or c.volume < 0:
            raise ValidationError(f'Invalid volume in candle {c.timestamp}')
