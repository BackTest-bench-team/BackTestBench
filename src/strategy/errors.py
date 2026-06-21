"""Exceptions raised by the Strategy Module."""

from __future__ import annotations


class StrategyError(Exception):
    """Base class for all Strategy Module errors."""


class UnknownStrategyError(StrategyError, KeyError):
    """Raised when a strategy name/ID is not present in the registry."""


class ConfigError(StrategyError, ValueError):
    """Raised when a strategy configuration is malformed or incomplete."""


class ParameterValidationError(StrategyError, ValueError):
    """Raised when a strategy's own parameters fail validation."""
