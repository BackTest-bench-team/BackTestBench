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
from .loader import (
    discover_builtin_strategies,
    load_plugin_file,
    load_plugins_from_dir,
)
from .schema import (
    ORDER_SIZE_MAX,
    ParameterSpec,
    describe_all,
    describe_strategy,
    order_size_spec,
    parameter_specs,
)
from .store import (
    delete_saved_config,
    list_saved_configs,
    load_saved_config,
    save_strategy_config,
)
from . import strategies  # noqa: F401  (auto-discovers & registers built-ins)

__all__ = [
    "BaseStrategy", "StrategyConfig", "load_config", "parse_config",
    "register_strategy", "create_strategy", "create_from_config",
    "get_strategy_class", "available_strategies", "is_registered", "clear_registry",
    "discover_builtin_strategies", "load_plugin_file", "load_plugins_from_dir",
    "ParameterSpec", "ORDER_SIZE_MAX", "order_size_spec",
    "describe_strategy", "describe_all", "parameter_specs",
    "save_strategy_config", "load_saved_config", "list_saved_configs", "delete_saved_config",
    "StrategyError", "UnknownStrategyError", "ConfigError", "ParameterValidationError",
]
