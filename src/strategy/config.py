"""Strategy configuration parser.

Loads strategy settings from YAML (or a plain dict) into a validated
``StrategyConfig``. Validates the envelope (name, instrument, timeframe, version,
params); strategy-specific parameter values inside ``params`` are validated by
the strategy itself (issue #44).

Config schema:
    name:        str   (required) — registered strategy ID
    instrument:  str   (optional) — ticker, e.g. "SBER"
    timeframe:   str   (optional) — "1m", "5m", "15m", "1h", "4h", "1d"
    version:     str   (optional, default "1")
    params:      dict  (optional, default {})
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError

_ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    name: str
    params: dict = field(default_factory=dict)
    instrument: str | None = None
    timeframe: str | None = None
    version: str = "1"


def parse_config(data: Mapping[str, Any]) -> StrategyConfig:
    if not isinstance(data, Mapping):
        raise ConfigError(f"config must be a mapping/object, got {type(data).__name__}")

    name = data.get("name")
    if not name or not isinstance(name, str):
        raise ConfigError("config field 'name' is required and must be a non-empty string")

    params = data.get("params", {})
    if not isinstance(params, dict):
        raise ConfigError(f"config field 'params' must be a mapping, got {type(params).__name__}")

    instrument = data.get("instrument")
    if instrument is not None and not isinstance(instrument, str):
        raise ConfigError("config field 'instrument' must be a string")

    timeframe = data.get("timeframe")
    if timeframe is not None:
        if not isinstance(timeframe, str):
            raise ConfigError("config field 'timeframe' must be a string")
        if timeframe not in _ALLOWED_TIMEFRAMES:
            raise ConfigError(
                f"unsupported timeframe '{timeframe}'; allowed: {sorted(_ALLOWED_TIMEFRAMES)}"
            )

    version = str(data.get("version", "1"))
    return StrategyConfig(name, dict(params), instrument, timeframe, version)


def load_config(path: str | Path) -> StrategyConfig:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("PyYAML is required to load YAML configs") from exc

    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"config file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {p}: {exc}") from exc
    if data is None:
        raise ConfigError(f"config file is empty: {p}")
    return parse_config(data)
