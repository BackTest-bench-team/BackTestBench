"""Action registry and handlers.

an action is what a fired rule does. Each handler has the signature
``(EvaluationContext, Action) -> Signal``. Built-in actions: buy, sell, hold.

Stop-loss / take-profit are not separate action types. They are optional fields
on ``buy`` (``stop_loss_pct`` / ``take_profit_pct``) or expressed as ordinary
rules (``loss_pct`` / ``profit_pct`` -> sell). If the engine's Portfolio exposes
an ``effects`` list, a ``buy`` carrying SL/TP appends a ``PositionEffect`` to it
so the engine can enforce the exit directly; if it does not, the equivalent
``loss_pct`` / ``profit_pct`` rules produce the same behaviour. Both paths are
supported, so this module works whether or not the engine tracks effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.engine.models import Signal
from src.engine.types import SignalType

from .context import EvaluationContext
from .errors import CompileError

_ACTIONS: dict[str, Callable] = {}


def register_action(name: str):
    def deco(fn: Callable) -> Callable:
        if name in _ACTIONS:
            raise ValueError(f"action '{name}' already registered")
        _ACTIONS[name] = fn
        return fn

    return deco


def action_names() -> list[str]:
    return sorted(_ACTIONS)


@dataclass
class Action:
    type: str
    size: float | str | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class PositionEffect:
    """A stop-loss / take-profit marker the engine can attach to a position."""
    kind: str          # "stop_loss" | "take_profit"
    value_pct: float


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
        extra=a,
    )


def run_action(ctx: EvaluationContext, action: Action) -> Signal:
    return _ACTIONS[action.type](ctx, action)


@register_action("buy")
def _buy(ctx: EvaluationContext, action: Action) -> Signal:
    size = 1.0 if action.size in (None, "all") else float(action.size)
    # if the portfolio tracks effects, record the SL/TP so the engine enforces it
    effects = getattr(ctx.portfolio, "effects", None)
    if effects is not None:
        if action.stop_loss_pct is not None:
            effects.append(PositionEffect("stop_loss", float(action.stop_loss_pct)))
        if action.take_profit_pct is not None:
            effects.append(PositionEffect("take_profit", float(action.take_profit_pct)))
    return Signal(type=SignalType.BUY, size=size)


@register_action("sell")
def _sell(ctx: EvaluationContext, action: Action) -> Signal:
    # "all" — the engine closes the full open position on a SELL
    return Signal(type=SignalType.SELL, size=getattr(ctx.portfolio, "position_size", 1.0) or 1.0)


@register_action("hold")
def _hold(ctx: EvaluationContext, action: Action) -> Signal:
    return Signal(type=SignalType.HOLD)
