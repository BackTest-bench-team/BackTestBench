"""First built-in strategy: moving-average crossover.

Long-only indicator strategy that runs on candle closes alone. It reads the
engine's ``ExecutionContext`` (current candle + historical candles + portfolio)
and returns one of the engine's ``Signal`` values each call.

Logic: fast SMA vs slow SMA of closes.
  * fast crosses ABOVE slow  -> BUY  (if flat)
  * fast crosses BELOW slow  -> SELL (if holding)
  * otherwise / during warmup -> HOLD

Computed statelessly from ``context.historical_candles`` + current candle, so it
does not depend on call order or need a reset between runs.

Parameters (under ``params`` in the YAML config):
  * fast        int   > 0, < slow   (default 10)
  * slow        int   > 0           (default 30)
  * order_size  float > 0           (default 1.0)  — emitted as Signal.size
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.models import Signal
from engine.types import SignalType

from ..base import BaseStrategy
from ..errors import ParameterValidationError
from ..registry import register_strategy

if TYPE_CHECKING:
    from engine.context import ExecutionContext


@register_strategy("ma_crossover")
class MACrossover(BaseStrategy):
    def validate_params(self) -> None:
        self.fast = self._positive_int("fast", 10)
        self.slow = self._positive_int("slow", 30)
        self.order_size = self._positive_number("order_size", 1.0)
        if self.fast >= self.slow:
            raise ParameterValidationError(
                f"'fast' ({self.fast}) must be strictly less than 'slow' ({self.slow})"
            )

    def _positive_int(self, key: str, default: int) -> int:
        value = self.params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ParameterValidationError(f"parameter '{key}' must be an integer, got {value!r}")
        if value < 1:
            raise ParameterValidationError(f"parameter '{key}' must be >= 1, got {value}")
        return value

    def _positive_number(self, key: str, default: float) -> float:
        value = self.params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParameterValidationError(f"parameter '{key}' must be a number, got {value!r}")
        if value <= 0:
            raise ParameterValidationError(f"parameter '{key}' must be > 0, got {value}")
        return float(value)

    def on_candle(self, context: "ExecutionContext") -> Signal:
        closes = [c.close for c in context.historical_candles]
        closes.append(context.current_candle.close)
        n = len(closes)

        # need slow+1 closes to compare this bar's SMAs against the previous bar's
        if n < self.slow + 1:
            return Signal(type=SignalType.HOLD)

        fast_now = sum(closes[n - self.fast:n]) / self.fast
        slow_now = sum(closes[n - self.slow:n]) / self.slow
        fast_prev = sum(closes[n - self.fast - 1:n - 1]) / self.fast
        slow_prev = sum(closes[n - self.slow - 1:n - 1]) / self.slow

        is_long = context.portfolio.position_size > 0
        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        if crossed_up and not is_long:
            return Signal(type=SignalType.BUY, size=self.order_size)
        if crossed_down and is_long:
            return Signal(type=SignalType.SELL, size=self.order_size)
        return Signal(type=SignalType.HOLD)
