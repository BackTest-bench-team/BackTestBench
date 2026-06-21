"""Strategy Module — public API."""

from __future__ import annotations

from .base import BaseStrategy
from .config import StrategyConfig, load_config, parse_config
from .errors import (
    ConfigError,
    ParameterValidationError,
    StrategyError,
    UnknownStrategyError,
)
from .registry import (
    available_strategies,
    clear_registry,
    create_from_config,
    create_strategy,
    get_strategy_class,
    is_registered,
    register_strategy,
)
from . import strategies  # noqa: F401  (registers built-ins on import)

__all__ = [
    "BaseStrategy", "StrategyConfig", "load_config", "parse_config",
    "register_strategy", "create_strategy", "create_from_config",
    "get_strategy_class", "available_strategies", "is_registered", "clear_registry",
    "StrategyError", "UnknownStrategyError", "ConfigError", "ParameterValidationError",
]
