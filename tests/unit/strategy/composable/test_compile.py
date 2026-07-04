"""Composable foundation: parse, compile, choices, optimize spec."""

from __future__ import annotations

import math

import pytest

from src.engine.context import ExecutionContext
from src.engine.models import Candle
from src.engine.portfolio import Portfolio
from src.strategy import (
    available_strategies, create_strategy, describe_strategy, get_strategy_class,
)
from src.strategy.composable import (
    CompileError, StrategyDefinition, compile_strategy, get_optimize_spec,
)

MIN_DEF = {
    "name": "mini",
    "params": {"period": {"type": "int", "default": 3, "choices": [2, 3, 5], "optimizable": True}},
    "series": {"ma": {"fn": "sma", "source": "price", "period": "${period}"}},
    "rules": [{"id": "e", "scope": "flat", "priority": 1,
               "when": {"gt": ["ma", 0]}, "then": {"action": "buy"}}],
}


def test_composable_registered_and_example_compiles():
    assert "composable" in available_strategies()
    d = StrategyDefinition.from_yaml("config/strategies/ma_rsi_composable.yaml")
    compiled = compile_strategy(d)                      # design  example compiles
    assert compiled.params["fast"] == 10
    assert any(n.id == "fast_ma" for n in compiled.nodes)


def test_param_substitution_resolves_choices():
    d = StrategyDefinition.from_dict(MIN_DEF)
    compiled = compile_strategy(d, overrides={"period": 5})
    assert compiled.params["period"] == 5
    assert compiled.nodes[0].params["period"] == 5      # ${period} substituted


def test_describe_maps_to_schema_with_choices():
    d = describe_strategy("ma_rsi_composable")
    fast = next(p for p in d["parameters"] if p["name"] == "fast")
    assert fast["choices"] == [5, 10, 12, 21, 30, 50]   # preset resolved
    assert fast["optimizable"] is True


def test_get_optimize_spec_grid():
    d = StrategyDefinition.from_dict(MIN_DEF)
    spec = get_optimize_spec(d)
    assert spec.params == {"period": [2, 3, 5]}
    assert spec.size() == 3


def test_preset_resolution():
    d = StrategyDefinition.from_yaml("config/strategies/ma_rsi_composable.yaml")
    assert d.params["slow"].choices == [20, 30, 50, 100, 200]   # preset:ma_long


# ---- clear errors at compile time -----------------------------------------
def _def(**over):
    base = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in MIN_DEF.items()}
    base.update(over)
    return base


def test_invalid_value_not_in_choices():
    with pytest.raises(CompileError):
        compile_strategy(StrategyDefinition.from_dict(MIN_DEF), overrides={"period": 4})


def test_unknown_param_override():
    with pytest.raises(CompileError):
        compile_strategy(StrategyDefinition.from_dict(MIN_DEF), overrides={"nope": 1})


def test_unknown_series_fn():
    bad = _def(series={"x": {"fn": "bogus", "source": "price"}})
    with pytest.raises(CompileError):
        compile_strategy(StrategyDefinition.from_dict(bad))


def test_unknown_param_reference():
    bad = _def(series={"x": {"fn": "sma", "source": "price", "period": "${ghost}"}})
    with pytest.raises(CompileError):
        compile_strategy(StrategyDefinition.from_dict(bad))


def test_missing_series_or_rules_rejected():
    with pytest.raises(CompileError):
        StrategyDefinition.from_dict({"name": "x", "series": {}, "rules": []})


def test_bad_scope_rejected():
    bad = _def(rules=[{"id": "e", "scope": "sideways", "priority": 1,
                       "when": {"gt": ["ma", 0]}, "then": {"action": "buy"}}])
    with pytest.raises(CompileError):
        compile_strategy(StrategyDefinition.from_dict(bad))
