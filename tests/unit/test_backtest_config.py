import pytest

from src.backtest_config import (
    ConfigValidationError,
    validate_lookback_days,
    validate_runtime_settings,
    validate_timeframe,
)


def test_validate_timeframe_rejects_subminute():
    with pytest.raises(ConfigValidationError):
        validate_timeframe("30s")


def test_validate_lookback_days_respects_limit():
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", 200)


def test_validate_runtime_settings_normalizes_instrument():
    result = validate_runtime_settings(
        {
            "instrument": "sber",
            "timeframe": "1h",
            "lookback_days": 30,
            "initial_capital": 100_000,
            "optimization_mode": "grid",
            "optimization_iterations": 16,
            "optimization_seed": 42,
        }
    )
    assert result["instrument"] == "SBER"
