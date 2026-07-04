"""errors raised while compiling or running a composable strategy."""

from __future__ import annotations

from ..errors import StrategyError


class CompileError(StrategyError, ValueError):
    """Raised when a composable YAML/config is invalid at compile time."""
