"""Composable strategy engine (config-driven strategies).

See docs/strategy_composable_engine_design.md. Public surface:
  - ComposableStrategy (registered as "composable")
  - register_composable_file / discover_composable_strategies
  - compile_strategy, get_optimize_spec
  - registries: register_series_fn, register_predicate, register_action
"""

from __future__ import annotations

from .actions import Action, PositionEffect, register_action, action_names
from .compile import CompiledStrategy, OptimizeSpec, compile_strategy, get_optimize_spec
from .constraints import check_constraints
from .context import EvaluationContext, StrategyState
from .definition import StrategyDefinition
from .errors import CompileError
from .predicates import compile_predicate, register_predicate, predicate_names
from .rules import Rule, compile_rules, evaluate_rules
from .series import (
    FloatSeries,
    SeriesNode,
    precompute,
    register_series_fn,
    series_fn_names,
    topological_order,
)
from .strategy import (
    ComposableStrategy,
    definition_to_specs,
    discover_composable_strategies,
    register_composable_file,
)

__all__ = [
    "ComposableStrategy", "StrategyDefinition", "CompiledStrategy", "compile_strategy",
    "OptimizeSpec", "get_optimize_spec", "register_composable_file", "check_constraints",
    "discover_composable_strategies", "definition_to_specs",
    "register_series_fn", "series_fn_names", "precompute", "topological_order",
    "SeriesNode", "FloatSeries",
    "register_predicate", "predicate_names", "compile_predicate",
    "register_action", "action_names", "Action", "PositionEffect",
    "Rule", "compile_rules", "evaluate_rules",
    "EvaluationContext", "StrategyState", "CompileError",
]
