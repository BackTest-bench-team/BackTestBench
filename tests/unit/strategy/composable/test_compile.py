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
    assert compiled.params["fast"] == 12
    assert any(n.id == "fast_ma" for n in compiled.nodes)


def test_param_substitution_resolves_choices():
    d = StrategyDefinition.from_dict(MIN_DEF)
    compiled = compile_strategy(d, overrides={"period": 5})
    assert compiled.params["period"] == 5
    assert compiled.nodes[0].params["period"] == 5      # ${period} substituted


def test_describe_maps_to_schema_with_choices():
    d = describe_strategy("ma_rsi_composable")
    fast = next(p for p in d["parameters"] if p["name"] == "fast")
    assert fast["choices"] == [5, 8, 10, 12, 21, 30, 50]   # preset resolved
    assert fast["optimizable"] is True


def test_get_optimize_spec_grid():
    d = StrategyDefinition.from_dict(MIN_DEF)
    spec = get_optimize_spec(d)
    assert spec.params == {"period": [2, 3, 5]}
    assert spec.size() == 3


def test_preset_resolution():
    d = StrategyDefinition.from_yaml("config/strategies/ma_rsi_composable.yaml")
    assert d.params["slow"].choices == [20, 30, 50, 100]   # preset:ma_long
    assert d.params["stop_loss_pct"].choices == [0.5, 0.7, 1.0, 1.5]
    assert d.params["take_profit_pct"].choices == [0.5, 1.0, 1.5, 2.0]


def test_ma_rsi_defaults_are_within_preset_choices():
    d = StrategyDefinition.from_yaml("config/strategies/ma_rsi_composable.yaml")
    compiled = compile_strategy(d)
    assert compiled.params["stop_loss_pct"] == 0.7
    assert compiled.params["take_profit_pct"] == 1.0
    assert compiled.params["stop_loss_pct"] in d.params["stop_loss_pct"].choices
    assert compiled.params["take_profit_pct"] in d.params["take_profit_pct"].choices


def test_sma_cross_demo_compiles_with_preset_defaults():
    d = StrategyDefinition.from_yaml("config/strategies/sma_cross_demo.yaml")
    compiled = compile_strategy(d)
    assert compiled.params["stop_loss_pct"] == 0.7
    assert compiled.params["take_profit_pct"] == 0.5


def test_get_optimize_spec_includes_tp_sl_from_presets():
    d = StrategyDefinition.from_yaml("config/strategies/ma_rsi_composable.yaml")
    spec = get_optimize_spec(d)
    assert spec.params["stop_loss_pct"] == [0.5, 0.7, 1.0, 1.5]
    assert spec.params["take_profit_pct"] == [0.5, 1.0, 1.5, 2.0]


def test_param_bounds_enforced_at_compile_time():
    bounded = {
        "name": "bounded",
        "params": {
            "x": {"type": "float", "default": 1.0, "min": 0.5, "max": 1.5},
        },
        "series": {"ma": {"fn": "sma", "source": "price", "period": 3}},
        "rules": [{"id": "e", "scope": "flat", "priority": 1,
                   "when": {"gt": ["ma", 0]}, "then": {"action": "buy"}}],
    }
    with pytest.raises(CompileError, match="> max"):
        compile_strategy(StrategyDefinition.from_dict(bounded), overrides={"x": 2.0})
    with pytest.raises(CompileError, match="< min"):
        compile_strategy(StrategyDefinition.from_dict(bounded), overrides={"x": 0.1})


def test_param_coercion_rejects_non_numeric_values():
    typed = {
        "name": "typed",
        "params": {
            "period": {"type": "int", "default": 3},
            "ratio": {"type": "float", "default": 1.0},
        },
        "series": {"ma": {"fn": "sma", "source": "price", "period": "${period}"}},
        "rules": [{"id": "e", "scope": "flat", "priority": 1,
                   "when": {"gt": ["ma", 0]}, "then": {"action": "buy"}}],
    }
    definition = StrategyDefinition.from_dict(typed)
    with pytest.raises(CompileError, match="must be an integer"):
        compile_strategy(definition, overrides={"period": "bad"})
    with pytest.raises(CompileError, match="must be a number"):
        compile_strategy(definition, overrides={"ratio": "bad"})


def test_definition_rejects_invalid_name_and_param_spec():
    with pytest.raises(CompileError, match="non-empty 'name'"):
        StrategyDefinition.from_dict({"name": "", "series": {"x": {}}, "rules": [{}]})
    with pytest.raises(CompileError, match="must be a mapping with a 'type'"):
        StrategyDefinition.from_dict(
            {"name": "bad", "params": {"x": "nope"}, "series": {"x": {}}, "rules": [{}]}
        )
    with pytest.raises(CompileError, match="optimizable but has no choices"):
        StrategyDefinition.from_dict(
            {
                "name": "bad",
                "params": {"x": {"type": "int", "default": 1, "optimizable": True}},
                "series": {"x": {"fn": "sma", "source": "price", "period": 3}},
                "rules": [{"id": "e", "scope": "flat", "priority": 1,
                           "when": {"gt": ["x", 0]}, "then": {"action": "buy"}}],
            }
        )


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
