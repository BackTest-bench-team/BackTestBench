"""Strategy base class.

Defines the abstraction the Execution Engine drives: it holds a BaseStrategy and
calls ``on_candle(context)`` once per candle, where ``context`` is the engine's
``ExecutionContext`` (``current_candle``, ``historical_candles``, ``portfolio``).
A strategy is built from a plain ``params`` dict and validates it on construction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # imported for typing only; no runtime dependency on the engine
    from src.engine.context import ExecutionContext
    from src.engine.models import Signal


class BaseStrategy(ABC):
    def __init__(self, params: dict):
        self.params = params
        self.validate_params()

    def validate_params(self) -> None:
        """Override to validate ``self.params`` and parse derived fields.

        Runs once, in ``__init__``. Should raise on bad input. Default: no-op.
        """

    @abstractmethod
    def on_candle(self, context: "ExecutionContext") -> "Signal":
        """Return exactly one Signal for the current candle.

        Deterministic, no I/O, no broker/DB access, and must not mutate the
        context or its portfolio.
        """
        raise NotImplementedError
