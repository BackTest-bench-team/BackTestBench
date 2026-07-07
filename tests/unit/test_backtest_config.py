import pytest

from src.backtest_config import (
    ConfigValidationError,
    normalize_instrument,
    ui_schema,
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


def test_validate_lookback_days_respects_limit():
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", 200)


def test_validate_lookback_days_rejects_non_positive():
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", 0)
    with pytest.raises(ConfigValidationError):
        validate_lookback_days("1h", True)


def test_normalize_instrument_uppercases_and_validates():
    assert normalize_instrument("sber") == "SBER"
    with pytest.raises(ConfigValidationError):
        normalize_instrument("")
    with pytest.raises(ConfigValidationError):
        normalize_instrument("FAKE")


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
    assert result["optimization_mode"] == "grid"


def test_ui_schema_exposes_instruments_and_defaults():
    schema = ui_schema()
    assert "SBER" in schema["instruments"]
    assert schema["defaults"]["timeframe"] == "1h"
    assert any(item["value"] == "grid" for item in schema["optimization_modes"])
