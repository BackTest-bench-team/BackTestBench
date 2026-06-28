"""Combined strategy: MA crossover with an RSI filter (customer request, 22-06).

The customer asked for a strategy where "a trade is opened only when the moving
averages indicate a trend AND RSI confirms an overbought/oversold condition" —
explicitly as a *new* strategy combining indicators, not a change to the
existing ma_crossover. This is that strategy.

Logic (long-only):
  * ENTER (BUY) when the fast SMA crosses ABOVE the slow SMA (uptrend) AND RSI
    is at/above ``rsi_buy_min`` (momentum confirms) — and we are flat.
  * EXIT (SELL) when the fast SMA crosses BELOW the slow SMA (downtrend) OR RSI
    is at/above ``rsi_overbought`` (overextended) — and we are holding.
  * otherwise / during warmup -> HOLD.

The RSI filter is what reduces poor entries: a crossover alone can fire in a
choppy market, but requiring RSI confirmation skips entries with weak momentum.

Parameters (under ``params``):
  * fast            int    > 0, < slow         (default 10)
  * slow            int    > 0                 (default 30)
  * rsi_period      int    >= 2                 (default 14)
  * rsi_buy_min     float  0..100               (default 50)  — min RSI to allow a BUY
  * rsi_overbought  float  0..100, > rsi_buy_min (default 70) — RSI exit trigger
  * order_size      float  > 0                  (default 1.0)
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


def _sma(closes: list[float], window: int, end: int) -> float:
    return sum(closes[end - window:end]) / window


def _rsi(closes: list[float], period: int) -> float:
    window = closes[-(period + 1):]
    gains = losses = 0.0
    for prev, cur in zip(window, window[1:]):
        delta = cur - prev
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain, avg_loss = gains / period, losses / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


@register_strategy("ma_rsi")
class MARSI(BaseStrategy):
    TITLE = "MA Crossover + RSI filter"
    PARAMS = [
        ParameterSpec("fast", "int", 10, minimum=1, description="Fast SMA window"),
        ParameterSpec("slow", "int", 30, minimum=2, description="Slow SMA window (> fast)"),
        ParameterSpec("rsi_period", "int", 14, minimum=2, description="RSI lookback window"),
        ParameterSpec("rsi_buy_min", "float", 50.0, minimum=0, maximum=100,
                      description="Minimum RSI required to confirm a BUY"),
        ParameterSpec("rsi_overbought", "float", 70.0, minimum=0, maximum=100,
                      description="RSI level that triggers an exit"),
        ParameterSpec("order_size", "float", 1.0, minimum=0, description="Order quantity"),
    ]

    def validate_params(self) -> None:
        self.fast = self._pos_int("fast", 10)
        self.slow = self._pos_int("slow", 30)
        if self.fast >= self.slow:
            raise ParameterValidationError(
                f"'fast' ({self.fast}) must be < 'slow' ({self.slow})"
            )
        self.rsi_period = self._pos_int("rsi_period", 14)
        if self.rsi_period < 2:
            raise ParameterValidationError(f"'rsi_period' must be >= 2, got {self.rsi_period}")
        self.rsi_buy_min = self._bounded("rsi_buy_min", 50.0)
        self.rsi_overbought = self._bounded("rsi_overbought", 70.0)
        if self.rsi_buy_min >= self.rsi_overbought:
            raise ParameterValidationError(
                f"'rsi_buy_min' ({self.rsi_buy_min}) must be < 'rsi_overbought' "
                f"({self.rsi_overbought})"
            )
        self.order_size = self._pos_num("order_size", 1.0)

    def _pos_int(self, key: str, default: int) -> int:
        v = self.params.get(key, default)
        if isinstance(v, bool) or not isinstance(v, int):
            raise ParameterValidationError(f"parameter '{key}' must be an integer, got {v!r}")
        if v < 1:
            raise ParameterValidationError(f"parameter '{key}' must be >= 1, got {v}")
        return v

    def _pos_num(self, key: str, default: float) -> float:
        v = self.params.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ParameterValidationError(f"parameter '{key}' must be a number, got {v!r}")
        if v <= 0:
            raise ParameterValidationError(f"parameter '{key}' must be > 0, got {v}")
        return float(v)

    def _bounded(self, key: str, default: float) -> float:
        v = self.params.get(key, default)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ParameterValidationError(f"parameter '{key}' must be a number, got {v!r}")
        if not (0 <= v <= 100):
            raise ParameterValidationError(f"parameter '{key}' must be within [0, 100], got {v}")
        return float(v)

    def on_candle(self, context: "ExecutionContext") -> Signal:
        closes = [c.close for c in context.historical_candles]
        closes.append(context.current_candle.close)
        n = len(closes)

        # need enough history for both the previous SMA pair and RSI
        if n < max(self.slow + 1, self.rsi_period + 1):
            return Signal(type=SignalType.HOLD)

        fast_now = _sma(closes, self.fast, n)
        slow_now = _sma(closes, self.slow, n)
        fast_prev = _sma(closes, self.fast, n - 1)
        slow_prev = _sma(closes, self.slow, n - 1)
        rsi = _rsi(closes, self.rsi_period)

        is_long = context.portfolio.position_size > 0
        crossed_up = fast_prev <= slow_prev and fast_now > slow_now
        crossed_down = fast_prev >= slow_prev and fast_now < slow_now

        # ENTER only when trend (crossover up) AND momentum (RSI) agree
        if crossed_up and rsi >= self.rsi_buy_min and not is_long:
            return Signal(type=SignalType.BUY, size=self.order_size)
        # EXIT on trend reversal OR overbought
        if is_long and (crossed_down or rsi >= self.rsi_overbought):
            return Signal(type=SignalType.SELL, size=self.order_size)
        return Signal(type=SignalType.HOLD)
