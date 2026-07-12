"""Trailing stop: move_stop action, trailing_stop_hit predicate, and E2E exit."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.engine import ExecutionEngine
from src.engine.models import Candle
from src.engine.portfolio import EffectType
from src.engine.types import SignalType
from src.strategy import create_strategy
from src.strategy.composable import Action, EvaluationContext
from src.strategy.composable.actions import is_terminal, run_action
from src.strategy.composable.context import StrategyState


@dataclass
class FakePortfolio:
    position_size: float = 10.0
    average_entry_price: float = 100.0
    effects: list = field(default_factory=list)
    def add_effect(self, e): self.effects.append(e)
    def clear_effects(self): self.effects = []


def ctx(price, state, prices=None):
    prices = prices or [price]
    return EvaluationContext(prices=prices, series={"price": prices}, index=len(prices) - 1,
                             timestamp="t", portfolio=FakePortfolio(), state=state)


def test_move_stop_is_non_terminal():
    assert is_terminal("move_stop") is False
    assert is_terminal("sell") is True


def test_move_stop_ratchets_up_and_sets_effect():
    state = StrategyState(peak_price=100)
    c = ctx(120, state, prices=[100, 110, 120])
    run_action(c, Action("move_stop", trailing_pct=10))
    assert state.peak_price == 120
    assert state.trailing_stop_level == 108.0            # 120 * 0.9
    # a single stop-loss effect is kept in sync for the engine
    sl = [e for e in c.portfolio.effects if e.type is EffectType.STOP_LOSS]
    assert len(sl) == 1 and sl[0].level == 108.0

    # price falls -> stop does NOT move down
    c2 = ctx(115, state, prices=[100, 110, 120, 115])
    run_action(c2, Action("move_stop", trailing_pct=10))
    assert state.trailing_stop_level == 108.0            # unchanged (ratchet only up)


def test_trailing_stop_hit_predicate():
    from src.strategy.composable import compile_predicate
    pred = compile_predicate({"trailing_stop_hit": True}, set())
    state = StrategyState(trailing_stop_level=108.0)
    assert pred(ctx(107, state)) is True     # below the stop
    assert pred(ctx(110, state)) is False    # above the stop


def test_trailing_stop_exits_in_backtest():
    definition = {
        "name": "trail",
        "params": {"fast": {"type": "int", "default": 3, "choices": [3]},
                   "slow": {"type": "int", "default": 6, "choices": [6]},
                   "tsp": {"type": "float", "default": 5, "choices": [5]}},
        "series": {"fast_ma": {"fn": "sma", "source": "price", "period": "${fast}"},
                   "slow_ma": {"fn": "sma", "source": "price", "period": "${slow}"}},
        "rules": [
            {"id": "trail", "scope": "long", "priority": 95,
             "when": {"has_position": True}, "then": {"action": "move_stop", "trailing_pct": "${tsp}"}},
            {"id": "exit", "scope": "long", "priority": 94,
             "when": {"trailing_stop_hit": True}, "then": {"action": "sell", "size": "all"}},
            {"id": "entry", "scope": "flat", "priority": 10,
             "when": {"cross_above": ["fast_ma", "slow_ma"]}, "then": {"action": "buy", "size": 1}},
        ],
    }
    prices = [100, 100, 100, 101, 103, 106, 110, 115, 121, 127, 133, 138, 142, 140, 133, 128, 120, 110]
    candles = [Candle(timestamp=str(i), open=p, high=p, low=p, close=p, volume=1000.0)
               for i, p in enumerate(prices)]
    strat = create_strategy("composable", {"definition": definition})
    result = ExecutionEngine().run(strat, candles, initial_capital=10_000.0)
    assert len(result["trade_log"]) >= 1
    # exited on the way down, not at the very last bar's bottom
    assert result["trade_log"][0].exit_price > prices[-1]
