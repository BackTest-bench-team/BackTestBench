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

from .errors import ParameterValidationError
from .registry import available_strategies, get_strategy_class

ORDER_SIZE_MAX = 3.0


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: str  # "int" | "float" | "str" | "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[Any] | None = None
    description: str = ""
    optimizable: bool = False

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None or k == "default"}


def order_size_spec(default: float = 1.0) -> ParameterSpec:
    """Shared order_size field — use in every strategy PARAMS list."""
    return ParameterSpec(
        "order_size",
        "float",
        default,
        minimum=1,
        maximum=ORDER_SIZE_MAX,
        description=f"Order quantity (1–{ORDER_SIZE_MAX:g} lots)",
    )


def parse_order_size(params: dict, default: float = 1.0, maximum: float = ORDER_SIZE_MAX) -> float:
    value = params.get("order_size", default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ParameterValidationError(f"parameter 'order_size' must be a number, got {value!r}")
    value = float(value)
    if value <= 0:
        raise ParameterValidationError(f"parameter 'order_size' must be > 0, got {value}")
    if value > maximum:
        raise ParameterValidationError(f"parameter 'order_size' must be <= {maximum}, got {value}")
    return value


def parameter_specs(strategy_id: str) -> list[ParameterSpec]:
    """The declared parameter specs for a strategy (empty list if none)."""
    cls = get_strategy_class(strategy_id)
    return list(getattr(cls, "PARAMS", []))


def validate_params_against_specs(strategy_id: str, params: dict) -> None:
    """Check user-supplied values against declared ParameterSpec bounds."""
    for spec in parameter_specs(strategy_id):
        if spec.name not in params:
            continue
        raw = params[spec.name]
        if spec.type == "int":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ParameterValidationError(
                    f"parameter '{spec.name}' must be an integer, got {raw!r}"
                )
            value: float | int = int(raw)
        elif spec.type == "float":
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ParameterValidationError(
                    f"parameter '{spec.name}' must be a number, got {raw!r}"
                )
            value = float(raw)
        else:
            continue
        if spec.minimum is not None and value < spec.minimum:
            raise ParameterValidationError(
                f"parameter '{spec.name}' must be >= {spec.minimum}, got {value}"
            )
        if spec.maximum is not None and value > spec.maximum:
            raise ParameterValidationError(
                f"parameter '{spec.name}' must be <= {spec.maximum}, got {value}"
            )


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
