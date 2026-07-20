import pytest

from src.backtest_config import (
    ConfigValidationError,
    normalize_instrument,
    ui_schema,
    validate_data_source,
    validate_initial_capital,
    validate_lookback_days,
    validate_optimization_iterations,
    validate_optimization_mode,
    validate_optimization_seed,
    validate_runtime_settings,
    validate_timeframe,
)


def test_validate_timeframe_rejects_subminute():
    with pytest.raises(ConfigValidationError):
        validate_timeframe("30s")


def test_validate_timeframe_rejects_empty_and_unknown():
    with pytest.raises(ConfigValidationError):
        validate_timeframe("")
    with pytest.raises(ConfigValidationError):
        validate_timeframe("2h")


def test_validate_lookback_days_allows_large_values():
    assert validate_lookback_days("1h", 10_000, data_source="tbank") == 10_000
    assert validate_lookback_days("1m", 365, data_source="bybit") == 365


def test_validate_lookback_days_rejects_excessive_value():
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", 500_000, data_source="tbank")


def test_validate_lookback_days_rejects_non_positive():
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", 0)
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", True)


def test_normalize_instrument_uppercases_and_validates_tbank():
    assert normalize_instrument("sber") == "SBER"
    with pytest.raises(ConfigValidationError):
        normalize_instrument("")
    with pytest.raises(ConfigValidationError):
        normalize_instrument("FAKE")


def test_normalize_instrument_validates_per_source():
    assert normalize_instrument("BTCUSDT", "bybit") == "BTCUSDT"
    with pytest.raises(ConfigValidationError):
        normalize_instrument("SBER", "bybit")
    assert normalize_instrument("AAPL", "twelvedata") == "AAPL"


def test_validate_data_source_rejects_unknown():
    assert validate_data_source("tbank") == "tbank"
    with pytest.raises(ConfigValidationError):
        validate_data_source("alpaca")


def test_validate_initial_capital_rejects_invalid_values():
    with pytest.raises(ConfigValidationError):
        validate_initial_capital("abc")
    with pytest.raises(ConfigValidationError):
        validate_initial_capital(0)
    with pytest.raises(ConfigValidationError):
        validate_initial_capital(2_000_000_000)


def test_validate_optimization_mode_and_iterations():
    assert validate_optimization_mode("grid") == "grid"
    with pytest.raises(ConfigValidationError):
        validate_optimization_mode("bruteforce")
    with pytest.raises(ConfigValidationError):
        validate_optimization_iterations("sample", 0)
    with pytest.raises(ConfigValidationError):
        validate_optimization_iterations("sample", 20_000)


def test_validate_optimization_seed_rejects_bool():
    with pytest.raises(ConfigValidationError):
        validate_optimization_seed(True)


def test_validate_runtime_settings_normalizes_instrument_and_source():
    result = validate_runtime_settings(
        {
            "data_source": "bybit",
            "instrument": "btcusdt",
            "timeframe": "1h",
            "lookback_days": 30,
            "initial_capital": 100_000,
            "optimization_mode": "grid",
            "optimization_iterations": 16,
            "optimization_seed": 42,
        }
    )
    assert result["instrument"] == "BTCUSDT"
    assert result["data_source"] == "bybit"
    assert result["optimization_mode"] == "grid"


def test_ui_schema_exposes_data_sources_and_defaults():
    schema = ui_schema()
    assert "SBER" in schema["instruments"]
    assert schema["defaults"]["timeframe"] == "1h"
    assert any(item["value"] == "grid" for item in schema["optimization_modes"])
    assert any(item["value"] == "tbank" for item in schema["data_sources"])
    bybit = next(item for item in schema["data_sources"] if item["value"] == "bybit")
    assert "BTCUSDT" in bybit["instruments"]
