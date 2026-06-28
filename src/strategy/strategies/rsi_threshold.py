"""Second built-in strategy: RSI threshold (issue #67).

A second independent indicator strategy, proving the module supports multiple
implementations through the same interface. Long-only, candle-only, fully
deterministic — same plugin contract as ``ma_crossover``.

RSI (Relative Strength Index) measures recent up-moves vs down-moves on a
0..100 scale. Low RSI = oversold (potential buy), high RSI = overbought
(potential sell).

Logic:
  * RSI <= oversold   and flat     -> BUY
  * RSI >= overbought and holding  -> SELL
  * otherwise / during warmup      -> HOLD

Parameters (under ``params``):
  * period      int    >= 2, < #candles   (default 14)  — RSI lookback
  * oversold    float  0..100, < overbought (default 30)
  * overbought  float  0..100, > oversold   (default 70)
  * order_size  float  > 0                  (default 1.0) — emitted as Signal.size
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.engine.models import Signal
from src.engine.types import SignalType

from ..base import BaseStrategy
from ..errors import ParameterValidationError
from ..registry import register_strategy
from ..schema import ParameterSpec

if TYPE_CHECKING:
    from src.engine.context import ExecutionContext


@register_strategy("rsi_threshold")
class RSIThreshold(BaseStrategy):
    TITLE = "RSI Threshold"
    PARAMS = [
        ParameterSpec("period", "int", 14, minimum=2, description="RSI lookback window (candles)"),
        ParameterSpec("oversold", "float", 30.0, minimum=0, maximum=100, description="Buy when RSI is at or below this"),
        ParameterSpec("overbought", "float", 70.0, minimum=0, maximum=100, description="Sell when RSI is at or above this"),
        ParameterSpec("order_size", "float", 1.0, minimum=0, description="Order quantity (Signal.size)"),
    ]

    def validate_params(self) -> None:
        self.period = self._positive_int("period", 14)
        if self.period < 2:
            raise ParameterValidationError(f"'period' must be >= 2, got {self.period}")
        self.oversold = self._bounded_number("oversold", 30.0)
        self.overbought = self._bounded_number("overbought", 70.0)
        if self.oversold >= self.overbought:
            raise ParameterValidationError(
                f"'oversold' ({self.oversold}) must be < 'overbought' ({self.overbought})"
            )
        self.order_size = self._positive_number("order_size", 1.0)

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

    def _bounded_number(self, key: str, default: float) -> float:
        value = self.params.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ParameterValidationError(f"parameter '{key}' must be a number, got {value!r}")
        if not (0 <= value <= 100):
            raise ParameterValidationError(f"parameter '{key}' must be within [0, 100], got {value}")
        return float(value)

    @staticmethod
    def _rsi(closes: list[float], period: int) -> float:
        window = closes[-(period + 1):]
        gains = losses = 0.0
        for prev, cur in zip(window, window[1:]):
            delta = cur - prev
            if delta >= 0:
                gains += delta
            else:
                losses -= delta
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def on_candle(self, context: "ExecutionContext") -> Signal:
        closes = [c.close for c in context.historical_candles]
        closes.append(context.current_candle.close)

        if len(closes) < self.period + 1:  # warmup
            return Signal(type=SignalType.HOLD)

        rsi = self._rsi(closes, self.period)
        is_long = context.portfolio.position_size > 0

        if rsi <= self.oversold and not is_long:
            return Signal(type=SignalType.BUY, size=self.order_size)
        if rsi >= self.overbought and is_long:
            return Signal(type=SignalType.SELL, size=self.order_size)
        return Signal(type=SignalType.HOLD)
