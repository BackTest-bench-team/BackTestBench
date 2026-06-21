"""Built-in strategy plugins. Importing this package registers them."""

from __future__ import annotations

from . import ma_crossover  # noqa: F401  (import triggers registration)

__all__ = ["ma_crossover"]
