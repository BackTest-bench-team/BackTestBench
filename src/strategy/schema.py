"""Parameter schemas for strategy configuration (issue #94).

A dashboard needs to know, for each strategy, which parameters it accepts so it
can render editable fields. Each strategy declares a list of ``ParameterSpec``
(name, type, default, bounds, description). ``describe_strategy`` /
``describe_all`` return JSON-serialisable schemas a frontend can consume to
"select strategies or parameters".

This module exposes *metadata only* — it never builds a UI. The dashboard
(frontend) reads these schemas; the strategy module stays headless.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .registry import available_strategies, get_strategy_class


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: str  # "int" | "float" | "str" | "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[Any] | None = None
    description: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None or k == "default"}


def parameter_specs(strategy_id: str) -> list[ParameterSpec]:
    """The declared parameter specs for a strategy (empty list if none)."""
    cls = get_strategy_class(strategy_id)
    return list(getattr(cls, "PARAMS", []))


def describe_strategy(strategy_id: str) -> dict:
    """JSON-serialisable description of one strategy and its editable params."""
    cls = get_strategy_class(strategy_id)
    return {
        "id": strategy_id,
        "title": getattr(cls, "TITLE", strategy_id),
        "description": (getattr(cls, "__doc__", "") or "").strip().split("\n")[0],
        "parameters": [spec.to_dict() for spec in parameter_specs(strategy_id)],
    }


def describe_all() -> list[dict]:
    """Description of every registered strategy — the dashboard's catalogue."""
    return [describe_strategy(name) for name in available_strategies()]
