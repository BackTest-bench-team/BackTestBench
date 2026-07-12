"""Cross-parameter constraints validated at compile time."""

from __future__ import annotations

import pytest

from src.strategy.composable import CompileError, StrategyDefinition, compile_strategy
from src.strategy.composable.constraints import check_constraints


def _def(constraints):
    return {
        "name": "c",
        "params": {
            "fast": {"type": "int", "default": 10, "choices": [5, 10, 30]},
            "slow": {"type": "int", "default": 30, "choices": [20, 30]},
            "stop_loss_pct": {"type": "float", "default": 5, "choices": [3, 5]},
            "take_profit_pct": {"type": "float", "default": 10, "choices": [8, 10]},
        },
        "constraints": constraints,
        "series": {"ma": {"fn": "sma", "source": "price", "period": "${fast}"}},
        "rules": [{"id": "e", "scope": "flat", "priority": 1,
                   "when": {"gt": ["ma", 0]}, "then": {"action": "buy"}}],
    }


def test_valid_constraints_pass():
    compile_strategy(StrategyDefinition.from_dict(_def(["fast < slow"])))


def test_violated_constraint_fails_at_compile():
    d = StrategyDefinition.from_dict(_def(["fast < slow"]))
    with pytest.raises(CompileError, match="constraint not satisfied"):
        compile_strategy(d, overrides={"fast": 30, "slow": 20})


def test_risk_reward_constraint():
    # take_profit must be at least twice the stop loss
    d = StrategyDefinition.from_dict(_def(["take_profit_pct >= 2 * stop_loss_pct"]))
    compile_strategy(d, overrides={"stop_loss_pct": 3, "take_profit_pct": 8})   # 8 >= 6 ok
    with pytest.raises(CompileError):
        compile_strategy(d, overrides={"stop_loss_pct": 5, "take_profit_pct": 8})  # 8 < 10


def test_helper_reusable_standalone():
    check_constraints(["a < b"], {"a": 1, "b": 2})
    with pytest.raises(CompileError):
        check_constraints(["a < b"], {"a": 2, "b": 1})


def test_unknown_param_in_constraint():
    with pytest.raises(CompileError, match="unknown parameter"):
        check_constraints(["ghost < b"], {"b": 1})


def test_bad_constraint_shape():
    with pytest.raises(CompileError):
        check_constraints(["fast slow"], {"fast": 1, "slow": 2})
