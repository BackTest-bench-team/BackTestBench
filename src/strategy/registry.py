"""Strategy registry and factory.

Stores available strategies and creates instances from configuration, so the
Execution Engine can load a strategy by name/ID without knowing its internals.
"""

from __future__ import annotations

from typing import Callable

from .base import BaseStrategy
from .config import StrategyConfig
from .errors import UnknownStrategyError

_REGISTRY: dict[str, type[BaseStrategy]] = {}


def register_strategy(name: str) -> Callable[[type[BaseStrategy]], type[BaseStrategy]]:
    """Class decorator that registers a strategy under ``name`` (its ID)."""

    def decorator(cls: type[BaseStrategy]) -> type[BaseStrategy]:
        if not (isinstance(cls, type) and issubclass(cls, BaseStrategy)):
            raise TypeError(f"{cls!r} must be a subclass of BaseStrategy")
        if name in _REGISTRY and _REGISTRY[name] is not cls:
            raise ValueError(
                f"strategy ID '{name}' already registered to {_REGISTRY[name].__name__}"
            )
        cls.strategy_id = name  # type: ignore[attr-defined]
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_strategy_class(name: str) -> type[BaseStrategy]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise UnknownStrategyError(
            f"no strategy registered under '{name}'. available: {available_strategies()}"
        ) from None


def create_strategy(name: str, params: dict | None = None) -> BaseStrategy:
    from .schema import validate_params_against_specs

    params = params or {}
    validate_params_against_specs(name, params)
    return get_strategy_class(name)(params)


def create_from_config(config: StrategyConfig) -> BaseStrategy:
    return create_strategy(config.name, config.params)


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


def is_registered(name: str) -> bool:
    return name in _REGISTRY


def clear_registry() -> None:
    """Empty the registry. Tests only."""
    _REGISTRY.clear()
