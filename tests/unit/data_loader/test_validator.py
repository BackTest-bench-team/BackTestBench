"""Validation and normalization for incoming candles."""
import pytest

from src.data_loader.normalizer import normalize_candle
from src.data_loader.validator import ValidationError, prepare_candles, validate_candles
from src.engine.models import Candle


def test_prepare_candles_filters_invalid_and_dedupes():
    candles = [
        Candle(timestamp="2025-01-01T10:00:00", open=1, high=2, low=0.5, close=1.5, volume=100),
        Candle(timestamp="2025-01-01T10:00:00", open=9, high=9, low=9, close=9, volume=200),
        Candle(timestamp="2025-01-01T11:00:00", open=None, high=2, low=1, close=1.5, volume=100),
        Candle(timestamp="2025-01-01T12:00:00", open=1, high=2, low=1, close=1.5, volume=-1),
        Candle(timestamp="2025-01-01T13:00:00", open=1, high=2, low=1, close=1.5, volume=None),
    ]
    cleaned = prepare_candles(candles)
    assert len(cleaned) == 2
    assert cleaned[0].timestamp == "2025-01-01T10:00:00"
    assert cleaned[0].close == 9
    assert cleaned[1].timestamp == "2025-01-01T13:00:00"
    assert cleaned[1].volume == 0.0


def test_normalize_candle_unifies_timezone_timestamp():
    c = normalize_candle(
        Candle(
            timestamp="2025-06-01T12:00:00+00:00",
            open="100",
            high=101,
            low=99,
            close=100.5,
            volume=None,
        )
    )
    assert c.timestamp == "2025-06-01T12:00:00"
    assert c.open == 100.0
    assert c.volume == 0.0


def test_validate_candles_raises_on_empty_or_all_invalid():
    with pytest.raises(ValidationError, match="empty"):
        validate_candles([])
    with pytest.raises(ValidationError, match="filtering"):
        validate_candles(
            [Candle(timestamp="2025-01-01T10:00:00", open=None, high=1, low=1, close=1, volume=1)]
        )
