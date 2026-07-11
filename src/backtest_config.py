"""Backtest dashboard settings: validation and UI schema."""

from __future__ import annotations

import os
from typing import Any

from src.broker_adapter.factory import (
    OPTIONAL_TOKEN_SOURCES,
    SUPPORTED_SOURCES,
    TOKEN_ENV_BY_SOURCE,
    source_display_name,
    token_configured,
)

TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M")
MIN_TIMEFRAME = "1m"

TBANK_INSTRUMENTS: tuple[str, ...] = (
    "SBER", "GAZP", "LKOH", "ROSN", "GMKN", "NVTK", "TATN", "VTBR",
    "YDEX", "OZON", "MGNT", "MTSS", "CHMF", "NLMK", "ALRS", "PLZL",
    "MOEX", "AFKS", "RUAL",
)

TWELVEDATA_INSTRUMENTS: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "SPY",
    "BTC/USD", "ETH/USD", "EUR/USD",
)

BYBIT_INSTRUMENTS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
    "BNBUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "MATICUSDT", "LTCUSDT",
    "SHIBUSDT", "TRXUSDT", "ATOMUSDT", "UNIUSDT", "NEARUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT",
)

INSTRUMENTS_BY_SOURCE: dict[str, tuple[str, ...]] = {
    "tbank": TBANK_INSTRUMENTS,
    "twelvedata": TWELVEDATA_INSTRUMENTS,
    "bybit": BYBIT_INSTRUMENTS,
}

DEFAULT_INSTRUMENT_BY_SOURCE: dict[str, str] = {
    "tbank": "SBER",
    "twelvedata": "AAPL",
    "bybit": "BTCUSDT",
}

# Backward-compatible alias used by older imports/tests.
INSTRUMENTS = TBANK_INSTRUMENTS
ALLOWED_INSTRUMENTS: frozenset[str] = frozenset(TBANK_INSTRUMENTS)
POPULAR_INSTRUMENTS = TBANK_INSTRUMENTS

DATA_SOURCE_META: dict[str, dict[str, Any]] = {
    "tbank": {
        "label": "T-Bank",
        "description": "MOEX TQBR shares via Tinkoff Invest API",
        "instrument_hint": "Russian equities on MOEX (SBER, GAZP, …)",
        "token_required": True,
    },
    "twelvedata": {
        "label": "Twelve Data",
        "description": "Global equities, FX and crypto via Twelve Data API",
        "instrument_hint": "US stocks, FX and crypto (AAPL, BTC/USD, …)",
        "token_required": True,
    },
    "bybit": {
        "label": "Bybit",
        "description": "Crypto spot pairs via Bybit public kline API",
        "instrument_hint": "Crypto spot pairs (BTCUSDT, ETHUSDT, …)",
        "token_required": False,
    },
}

TBANK_DAYS_LIMIT_BY_TIMEFRAME: dict[str, int] = {
    "1m": 1,
    "5m": 7,
    "15m": 24,
    "30m": 25,
    "1h": 100,
    "1d": 2400,
    "1w": 2100,
    "1M": 3600,
}

REMOTE_MAX_LOOKBACK_DAYS = 3650

# Backward-compatible alias.
DAYS_LIMIT_BY_TIMEFRAME = TBANK_DAYS_LIMIT_BY_TIMEFRAME

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


class ConfigValidationError(ValueError):
    pass


def validate_data_source(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized not in SUPPORTED_SOURCES:
        raise ConfigValidationError(
            f"data_source must be one of: {', '.join(SUPPORTED_SOURCES)}"
        )
    return normalized


def max_lookback_days(data_source: str, timeframe: str) -> int:
    source = validate_data_source(data_source)
    if source == "tbank":
        return TBANK_DAYS_LIMIT_BY_TIMEFRAME[timeframe]
    return REMOTE_MAX_LOOKBACK_DAYS


def normalize_instrument(instrument: str, data_source: str = "tbank") -> str:
    source = validate_data_source(data_source)
    if not isinstance(instrument, str) or not instrument.strip():
        raise ConfigValidationError("instrument must be a non-empty string")

    normalized = instrument.strip().upper()
    allowed = INSTRUMENTS_BY_SOURCE[source]
    if normalized not in allowed:
        allowed_list = ", ".join(allowed)
        raise ConfigValidationError(
            f"invalid instrument {instrument!r} for {source_display_name(source)}; "
            f"choose one of: {allowed_list}"
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


def validate_lookback_days(timeframe: str, lookback_days: int, data_source: str = "tbank") -> int:
    if isinstance(lookback_days, bool) or not isinstance(lookback_days, int):
        raise ConfigValidationError(f"lookback_days must be a positive integer, got: {lookback_days!r}")
    if lookback_days <= 0:
        raise ConfigValidationError(f"lookback_days must be > 0, got: {lookback_days}")

    source = validate_data_source(data_source)
    limit = max_lookback_days(source, timeframe)
    if lookback_days > limit:
        provider = source_display_name(source)
        raise ConfigValidationError(
            f"lookback_days={lookback_days} exceeds the limit for timeframe '{timeframe}' "
            f"on {provider} (max {limit} days)."
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
    data_source = validate_data_source(str(raw.get("data_source", "tbank")))
    instrument = normalize_instrument(
        str(raw.get("instrument", DEFAULT_INSTRUMENT_BY_SOURCE[data_source])),
        data_source=data_source,
    )
    timeframe = validate_timeframe(str(raw.get("timeframe", "1h")))
    lookback_days = validate_lookback_days(
        timeframe,
        int(raw.get("lookback_days", 30)),
        data_source=data_source,
    )
    initial_capital = validate_initial_capital(raw.get("initial_capital", 100_000))
    optimization_mode = validate_optimization_mode(str(raw.get("optimization_mode", "grid")))
    optimization_iterations = validate_optimization_iterations(
        optimization_mode,
        int(raw.get("optimization_iterations", 16)),
    )
    optimization_seed = validate_optimization_seed(int(raw.get("optimization_seed", 42)))

    return {
        "data_source": data_source,
        "instrument": instrument,
        "timeframe": timeframe,
        "lookback_days": lookback_days,
        "initial_capital": initial_capital,
        "optimization_mode": optimization_mode,
        "optimization_iterations": optimization_iterations,
        "optimization_seed": optimization_seed,
    }


def _timeframes_for_source(data_source: str) -> list[dict[str, int | str]]:
    return [
        {"value": tf, "max_lookback_days": max_lookback_days(data_source, tf)}
        for tf in TIMEFRAMES
    ]


def ui_schema() -> dict[str, Any]:
    data_sources = []
    for key in SUPPORTED_SOURCES:
        meta = DATA_SOURCE_META[key]
        data_sources.append(
            {
                "value": key,
                "label": meta["label"],
                "description": meta["description"],
                "instrument_hint": meta["instrument_hint"],
                "token_env": TOKEN_ENV_BY_SOURCE[key],
                "token_required": meta["token_required"],
                "token_optional": key in OPTIONAL_TOKEN_SOURCES,
                "token_configured": token_configured(key),
                "instruments": list(INSTRUMENTS_BY_SOURCE[key]),
                "default_instrument": DEFAULT_INSTRUMENT_BY_SOURCE[key],
                "timeframes": _timeframes_for_source(key),
            }
        )

    return {
        "data_sources": data_sources,
        "instruments": list(TBANK_INSTRUMENTS),
        "timeframes": _timeframes_for_source("tbank"),
        "optimization_modes": [
            {"value": mode_key, "description": desc}
            for mode_key, desc in OPTIMIZATION_MODES.items()
        ],
        "defaults": {
            "data_source": "tbank",
            "instrument": "SBER",
            "timeframe": "1h",
            "lookback_days": 30,
            "initial_capital": 100_000,
            "optimization_mode": "grid",
            "optimization_iterations": 16,
            "optimization_seed": 42,
        },
    }
