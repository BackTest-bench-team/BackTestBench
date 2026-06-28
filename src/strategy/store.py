"""Saved-strategy store (issue #94).

Lets a user take a strategy, edit its parameters, and SAVE the result as a new
named item (a JSON file). Saved items can be listed, loaded, and deleted — this
is the persistence layer a dashboard calls behind its "Save" button.

A saved item is a small JSON document:

    {
      "saved_name": "aggressive_ma",     # user-chosen label for this item
      "name":       "ma_crossover",      # which registered strategy
      "params":     {"fast": 3, "slow": 10, "order_size": 1.0},
      "instrument": "SBER",
      "timeframe":  "1m",
      "version":    "1"
    }

The "name"/"params" shape is exactly what ``parse_config`` accepts, so a saved
item loads straight back into a ``StrategyConfig`` and runs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .config import StrategyConfig, parse_config
from .errors import ConfigError
from .registry import create_strategy

DEFAULT_STORE_DIR = Path("config/saved_strategies")

_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_saved_name(saved_name: str) -> str:
    if not saved_name or not _SAFE_NAME.match(saved_name):
        raise ConfigError(
            f"invalid saved name {saved_name!r}; use letters, digits, '.', '_', '-'"
        )
    return saved_name


def save_strategy_config(
    saved_name: str,
    config: StrategyConfig | dict,
    *,
    directory: str | Path = DEFAULT_STORE_DIR,
    overwrite: bool = True,
) -> Path:
    """Validate a strategy configuration and save it as a named JSON item.

    Validation = parse the envelope AND construct the strategy, so a config that
    the strategy itself would reject (bad thresholds, fast>=slow, ...) is never
    written to disk.
    """
    _validate_saved_name(saved_name)

    cfg = config if isinstance(config, StrategyConfig) else parse_config(config)
    create_strategy(cfg.name, cfg.params)  # raises if params are invalid

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{saved_name}.json"
    if path.exists() and not overwrite:
        raise ConfigError(f"saved strategy '{saved_name}' already exists")

    payload = {
        "saved_name": saved_name,
        "name": cfg.name,
        "params": cfg.params,
        "instrument": cfg.instrument,
        "timeframe": cfg.timeframe,
        "version": cfg.version,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def list_saved_configs(directory: str | Path = DEFAULT_STORE_DIR) -> list[str]:
    directory = Path(directory)
    if not directory.is_dir():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def load_saved_config(
    saved_name: str, directory: str | Path = DEFAULT_STORE_DIR
) -> StrategyConfig:
    path = Path(directory) / f"{saved_name}.json"
    if not path.is_file():
        raise ConfigError(f"saved strategy '{saved_name}' not found in {directory}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"corrupt saved strategy '{saved_name}': {exc}") from exc
    return parse_config(data)


def delete_saved_config(
    saved_name: str, directory: str | Path = DEFAULT_STORE_DIR
) -> bool:
    path = Path(directory) / f"{saved_name}.json"
    if path.is_file():
        path.unlink()
        return True
    return False
