"""Compile a StrategyDefinition into a runnable CompiledStrategy.

compilation runs once when a strategy is loaded and:
  * resolves parameter values (defaults plus any overrides) and validates them
    against each param's choices and bounds;
  * substitutes ``${param}`` placeholders throughout the series and rules;
  * builds the series DAG (topological order, with cycle and unknown-input checks);
  * turns each ``when`` block into a predicate and each ``then`` into an action,
    sorted by priority.

Anything structurally wrong raises ``CompileError`` here, at load time, rather
than failing partway through a backtest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .constraints import check_constraints
from .definition import ParamDef, StrategyDefinition
from .errors import CompileError
from .rules import Rule, compile_rules, evaluate_rules
from .series import SeriesNode, build_nodes, precompute
from src.engine.models import Signal

_PLACEHOLDER = re.compile(r"^\$\{(\w+)\}$")


def _coerce(pdef: ParamDef, value):
    if pdef.type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CompileError(f"param '{pdef.name}' must be an integer, got {value!r}")
        return int(value)
    if pdef.type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise CompileError(f"param '{pdef.name}' must be a number, got {value!r}")
        return float(value)
    return value


def resolve_params(definition: StrategyDefinition, overrides: dict | None) -> dict:
    overrides = overrides or {}
    unknown = set(overrides) - set(definition.params)
    if unknown:
        raise CompileError(f"unknown param override(s): {sorted(unknown)}")
    resolved: dict = {}
    for name, pdef in definition.params.items():
        value = _coerce(pdef, overrides.get(name, pdef.default))
        if pdef.choices is not None and value not in pdef.choices:
            raise CompileError(
                f"param '{name}'={value} not in choices {pdef.choices}"
            )
        if pdef.minimum is not None and value < pdef.minimum:
            raise CompileError(f"param '{name}'={value} < min {pdef.minimum}")
        if pdef.maximum is not None and value > pdef.maximum:
            raise CompileError(f"param '{name}'={value} > max {pdef.maximum}")
        resolved[name] = value
    return resolved


def _substitute(obj, params: dict):
    if isinstance(obj, str):
        m = _PLACEHOLDER.match(obj)
        if m:
            key = m.group(1)
            if key not in params:
                raise CompileError(f"unknown parameter reference '${{{key}}}'")
            return params[key]
        return obj
    if isinstance(obj, list):
        return [_substitute(x, params) for x in obj]
    if isinstance(obj, dict):
        return {k: _substitute(v, params) for k, v in obj.items()}
    return obj


@dataclass
class CompiledStrategy:
    definition: StrategyDefinition
    params: dict
    nodes: list[SeriesNode]
    rules: list[Rule]

    def compute_series(self, prices: list[float]) -> dict[str, list[float]]:
        return precompute(self.nodes, prices)

    def evaluate(self, ctx) -> Signal:
        return evaluate_rules(self.rules, ctx)


def compile_strategy(definition: StrategyDefinition, overrides: dict | None = None) -> CompiledStrategy:
    params = resolve_params(definition, overrides)
    check_constraints(definition.constraints, params)
    series_cfg = _substitute(definition.series, params)
    rules_cfg = _substitute(definition.rules, params)

    nodes = build_nodes(series_cfg)
    series_ids = {n.id for n in nodes} | {"price"}
    rules = compile_rules(rules_cfg, series_ids)
    return CompiledStrategy(definition, params, nodes, rules)


# ---- optimizer spec --------------------------------------------------------
@dataclass
class OptimizeSpec:
    strategy_id: str
    params: dict[str, list]   # optimizable param -> choices

    def size(self) -> int:
        n = 1
        for choices in self.params.values():
            n *= len(choices)
        return n


def get_optimize_spec(definition: StrategyDefinition) -> OptimizeSpec:
    grid = {name: list(p.choices) for name, p in definition.params.items()
            if p.optimizable and p.choices}
    return OptimizeSpec(strategy_id=definition.name, params=grid)
