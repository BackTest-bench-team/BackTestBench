"""Action registry and handlers.

An action is what a fired rule does. Each handler has the signature
``(EvaluationContext, Action) -> Signal``. Built-in actions: buy, sell, hold,
and move_stop (trailing stop).

Stop-loss / take-profit are not separate action types. They are optional fields
on ``buy`` (``stop_loss_pct`` / ``take_profit_pct``) or expressed as ordinary
rules (``loss_pct`` / ``profit_pct`` -> sell). When SL/TP are set on ``buy`` the
handler also records ``PositionEffect`` entries on the portfolio (a stop-loss /
take-profit price level) which the engine can enforce directly; the equivalent
rules produce the same behaviour on their own.

``move_stop`` maintains a trailing stop: as price rises it ratchets a stop-loss
level up to ``peak * (1 - trailing_pct/100)``. It updates the trailing level on
the context state and keeps a single stop-loss ``PositionEffect`` in sync, so the
engine enforces the trailing exit and a rule can also act on it. Because it only
updates state (it does not itself open or close a position) it is a *non-terminal*
action: after it runs, rule evaluation continues so a lower-priority exit rule can
still fire on the same bar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.engine.models import Signal
from src.engine.types import SignalType
from src.engine.portfolio import EffectType, PositionEffect

from .context import EvaluationContext
from .errors import CompileError

_ACTIONS: dict[str, Callable] = {}

# actions that only update state/effects and must not end the bar's evaluation
NON_TERMINAL = {"move_stop"}


def register_action(name: str):
    def deco(fn: Callable) -> Callable:
        if name in _ACTIONS:
            raise ValueError(f"action '{name}' already registered")
        _ACTIONS[name] = fn
        return fn

    return deco


def action_names() -> list[str]:
    return sorted(_ACTIONS)


def is_terminal(action_type: str) -> bool:
    return action_type not in NON_TERMINAL


@dataclass
class Action:
    type: str
    size: float | str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_pct: float | None = None
    extra: dict = field(default_factory=dict)


def parse_action(then: dict) -> Action:
    if not isinstance(then, dict) or "action" not in then:
        raise CompileError(f"'then' must be a mapping with an 'action', got {then!r}")
    a = dict(then)
    atype = a.pop("action")
    if atype not in _ACTIONS:
        raise CompileError(f"unknown action '{atype}'; known: {action_names()}")
    return Action(
        type=atype,
        size=a.pop("size", None),
        stop_loss_pct=a.pop("stop_loss_pct", None),
        take_profit_pct=a.pop("take_profit_pct", None),
        trailing_pct=a.pop("trailing_pct", None),
        extra=a,
    )


def run_action(ctx: EvaluationContext, action: Action) -> Signal:
    return _ACTIONS[action.type](ctx, action)


def _add_effect(ctx: EvaluationContext, effect_type: EffectType, level: float) -> None:
    portfolio = ctx.portfolio
    if hasattr(portfolio, "add_effect"):
        portfolio.add_effect(PositionEffect(type=effect_type, level=level, size=1.0))


@register_action("buy")
def _buy(ctx: EvaluationContext, action: Action) -> Signal:
    size = 1.0 if action.size in (None, "all") else float(action.size)
    entry = ctx.price  # the engine fills the buy at the current close
    if action.stop_loss_pct is not None:
        _add_effect(ctx, EffectType.STOP_LOSS, entry * (1 - float(action.stop_loss_pct) / 100.0))
    if action.take_profit_pct is not None:
        _add_effect(ctx, EffectType.TAKE_PROFIT, entry * (1 + float(action.take_profit_pct) / 100.0))
    return Signal(type=SignalType.BUY, size=size)


@register_action("sell")
def _sell(ctx: EvaluationContext, action: Action) -> Signal:
    # "all" — the engine closes the full open position on a SELL
    return Signal(type=SignalType.SELL, size=getattr(ctx.portfolio, "position_size", 1.0) or 1.0)


@register_action("hold")
def _hold(ctx: EvaluationContext, action: Action) -> Signal:
    return Signal(type=SignalType.HOLD)


@register_action("move_stop")
def _move_stop(ctx: EvaluationContext, action: Action) -> Signal:
    """Ratchet a trailing stop up as price rises. Non-terminal."""
    if action.trailing_pct is None:
        raise CompileError("move_stop requires 'trailing_pct'")
    trailing = float(action.trailing_pct)
    state = ctx.state
    peak = state.peak_price if state.peak_price is not None else ctx.price
    peak = max(peak, ctx.price)
    state.peak_price = peak
    new_level = peak * (1 - trailing / 100.0)
    # only ever move the stop up
    if state.trailing_stop_level is None or new_level > state.trailing_stop_level:
        state.trailing_stop_level = new_level
    # keep a single stop-loss effect in sync for engine-side enforcement
    portfolio = ctx.portfolio
    if hasattr(portfolio, "effects"):
        portfolio.effects = [e for e in portfolio.effects
                             if getattr(e, "type", None) != EffectType.STOP_LOSS]
        _add_effect(ctx, EffectType.STOP_LOSS, state.trailing_stop_level)
    return Signal(type=SignalType.HOLD)
