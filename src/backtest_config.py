"""Backtest dashboard settings: validation and UI schema.

Mirrors the rules documented in examples/tbank_adapter_usage.py (PR #103).
"""

from __future__ import annotations

from typing import Any

TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M")
MIN_TIMEFRAME = "1m"

# MOEX TQBR tickers documented in examples/README.md (T-Bank adapter usage).
INSTRUMENTS: tuple[str, ...] = (
    "SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "VTBR",
    "YDEX", "OZON", "MGNT", "MTSS", "CHMF", "NLMK", "ALRS", "PLZL",
    "MOEX", "AFKS", "RUAL",
)

ALLOWED_INSTRUMENTS: frozenset[str] = frozenset(INSTRUMENTS)

POPULAR_INSTRUMENTS = INSTRUMENTS


class ConfigValidationError(ValueError):
    pass

DAYS_LIMIT_BY_TIMEFRAME: dict[str, int] = {
    "1m": 1,
    "5m": 7,
    "15m": 24,
    "30m": 25,
    "1h": 100,
    "1d": 2400,
    "1w": 2100,
    "1M": 3600,
}

OPTIMIZATION_MODES: dict[str, str] = {
    "grid": (
        "Full grid search - evaluates every valid parameter combination from "
        "YAML choices. Guarantees the best result on the current dataset; "
        "can take several minutes."
    ),
    "sample": (
        "Random sample - evaluates N random combinations (see iterations + seed). "
        "Faster, but does not guarantee the global optimum."
    ),
}

def normalize_instrument(instrument: str) -> str:
    if not isinstance(instrument, str) or not instrument.strip():
        raise ConfigValidationError("instrument must be a non-empty string")
    normalized = instrument.strip().upper()
    if normalized not in ALLOWED_INSTRUMENTS:
        allowed = ", ".join(sorted(ALLOWED_INSTRUMENTS))
        raise ConfigValidationError(
            f"invalid instrument {instrument!r}; choose one of: {allowed}"
        )
    return normalized


def validate_timeframe(timeframe: str) -> str:
    if not isinstance(timeframe, str) or not timeframe.strip():
        raise ConfigValidationError(f"timeframe must be a non-empty string, got: {timeframe!r}")

    normalized = timeframe.strip()
    if normalized.endswith("s"):
        raise ConfigValidationError(
            f"Unsupported timeframe {timeframe!r}: minimum resolution is '{MIN_TIMEFRAME}'"
        )
    if normalized not in TIMEFRAMES:
        raise ConfigValidationError(
            f"Unsupported timeframe {timeframe!r}. Supported: {', '.join(TIMEFRAMES)}"
        )
    return normalized


def validate_lookback_days(timeframe: str, lookback_days: int) -> int:
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int):
        raise ConfigValidationError(f"lookback_days must be a positive integer, got: {lookback_days!r}")
    if lookback_days <= 0:
        raise ConfigValidationError(f"lookback_days must be > 0, got: {lookback_days}")

    limit = DAYS_LIMIT_BY_TIMEFRAME[timeframe]
    if lookback_days > limit:
        raise ConfigValidationError(
            f"lookback_days={lookback_days} exceeds the limit for timeframe '{timeframe}' "
            f"(max {limit} days for T-Bank data)."
        )
    return lookback_days


def validate_initial_capital(value: Any) -> float:
    try:
        capital = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError("initial_capital must be a number") from exc
    if capital <= 0:
        raise ConfigValidationError("initial_capital must be > 0")
    if capital > 1_000_000_000:
        raise ConfigValidationError("initial_capital is unreasonably large")
    return capital


def validate_optimization_mode(mode: str) -> str:
    if mode not in OPTIMIZATION_MODES:
        raise ConfigValidationError(
            f"optimization_mode must be one of: {', '.join(OPTIMIZATION_MODES)}"
        )
    return mode


def validate_optimization_iterations(mode: str, iterations: int) -> int:
    if isinstance(iterations, bool) or not isinstance(iterations, int):
        raise ConfigValidationError(
            f"optimization_iterations must be a positive integer, got: {iterations!r}"
        )
    if iterations <= 0:
        raise ConfigValidationError("optimization_iterations must be > 0")
    if mode == "sample" and iterations > 10_000:
        raise ConfigValidationError("optimization_iterations must be <= 10000 in sample mode")
    return iterations


def validate_optimization_seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ConfigValidationError(f"optimization_seed must be an integer, got: {seed!r}")
    return seed


def validate_runtime_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize dashboard runtime settings (not strategy params)."""
    instrument = normalize_instrument(str(raw.get("instrument", "SBER")))
    timeframe = validate_timeframe(str(raw.get("timeframe", "1h")))
    lookback_days = validate_lookback_days(timeframe, int(raw.get("lookback_days", 30)))
    initial_capital = validate_initial_capital(raw.get("initial_capital", 100_000))
    optimization_mode = validate_optimization_mode(str(raw.get("optimization_mode", "grid")))
    optimization_iterations = validate_optimization_iterations(
        optimization_mode,
        int(raw.get("optimization_iterations", 16)),
    )
    optimization_seed = validate_optimization_seed(int(raw.get("optimization_seed", 42)))

    return {
        "instrument": instrument,
        "timeframe": timeframe,
        "lookback_days": lookback_days,
        "initial_capital": initial_capital,
        "optimization_mode": optimization_mode,
        "optimization_iterations": optimization_iterations,
        "optimization_seed": optimization_seed,
    }


def ui_schema() -> dict[str, Any]:
    return {
        "instruments": list(INSTRUMENTS),
        "timeframes": [
            {"value": tf, "max_lookback_days": DAYS_LIMIT_BY_TIMEFRAME[tf]}
            for tf in TIMEFRAMES
        ],
        "optimization_modes": [
            {"value": key, "description": desc}
            for key, desc in OPTIMIZATION_MODES.items()
        ],
        "defaults": {
            "instrument": "SBER",
            "timeframe": "1h",
            "lookback_days": 30,
            "initial_capital": 100_000,
            "optimization_mode": "grid",
            "optimization_iterations": 16,
            "optimization_seed": 42,
        },
    }
