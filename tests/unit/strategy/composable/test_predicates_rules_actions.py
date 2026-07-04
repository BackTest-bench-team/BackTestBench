"""Predicates, rules, actions."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.engine.types import SignalType
from src.strategy.composable import (
    Action, EvaluationContext, action_names, compile_predicate, compile_rules,
    evaluate_rules, predicate_names,
)
from src.strategy.composable.actions import run_action


@dataclass
class FakePortfolio:
    position_size: float = 0.0
    average_entry_price: float = 0.0


def ctx(series, i, portfolio=None, prices=None):
    prices = prices or series.get("price", [0] * (i + 1))
    return EvaluationContext(prices=prices, series=series, index=i, timestamp="t",
                             portfolio=portfolio or FakePortfolio())


def test_p0_predicates_and_actions_registered():
    for p in ("gt", "lt", "gte", "lte", "cross_above", "cross_below",
              "all", "not", "has_position", "profit_pct", "loss_pct"):
        # all/any/not are handled by the compiler; the rest are in the registry
        if p in ("all", "any", "not"):
            continue
        assert p in predicate_names()
    for a in ("buy", "sell", "hold"):
        assert a in action_names()


def test_comparison_and_series_operand():
    series = {"rsi": [10, 80, 40]}
    pred = compile_predicate({"gte": ["rsi", 70]}, {"rsi"})
    assert pred(ctx(series, 1)) is True
    assert pred(ctx(series, 2)) is False


def test_cross_above():
    series = {"a": [1, 1, 3], "b": [2, 2, 2]}
    pred = compile_predicate({"cross_above": ["a", "b"]}, {"a", "b"})
    assert pred(ctx(series, 1)) is False   # 1 vs 2, no cross
    assert pred(ctx(series, 2)) is True    # crossed 1<=2 then 3>2


def test_all_any_not():
    series = {"x": [5], "y": [1]}
    assert compile_predicate({"all": [{"gt": ["x", 0]}, {"lt": ["y", 2]}]}, {"x", "y"})(ctx(series, 0))
    assert compile_predicate({"any": [{"gt": ["x", 99]}, {"lt": ["y", 2]}]}, {"x", "y"})(ctx(series, 0))
    assert compile_predicate({"not": {"gt": ["x", 99]}}, {"x"})(ctx(series, 0))


def test_loss_pct_predicate():
    series = {"price": [100, 90]}
    pf = FakePortfolio(position_size=10, average_entry_price=100)
    pred = compile_predicate({"loss_pct": {"gt": 5}}, set())
    assert pred(ctx(series, 1, pf)) is True     # 10% loss > 5
    assert pred(ctx(series, 1, FakePortfolio())) is False  # flat -> false


def test_actions_return_expected_signals():
    c = ctx({"price": [100]}, 0, FakePortfolio(position_size=5, average_entry_price=100))
    assert run_action(c, Action("buy", size=2)).type is SignalType.BUY
    assert run_action(c, Action("sell", size="all")).type is SignalType.SELL
    assert run_action(c, Action("hold")).type is SignalType.HOLD


def test_rule_scope_and_priority_first_match_wins():
    rules_cfg = [
        {"id": "sl", "scope": "long", "priority": 100,
         "when": {"loss_pct": {"gt": 5}}, "then": {"action": "sell", "size": "all"}},
        {"id": "exit", "scope": "long", "priority": 10,
         "when": {"gte": ["rsi", 70]}, "then": {"action": "sell"}},
        {"id": "entry", "scope": "flat", "priority": 10,
         "when": {"gte": ["rsi", 50]}, "then": {"action": "buy"}},
    ]
    rules = compile_rules(rules_cfg, {"rsi"})
    assert [r.id for r in rules][0] == "sl"   # sorted priority desc

    # flat scope: only entry eligible
    flat = ctx({"rsi": [60], "price": [100]}, 0, FakePortfolio())
    assert evaluate_rules(rules, flat).type is SignalType.BUY

    # long + big loss: stop_loss (priority 100) wins over signal exit
    long_loss = ctx({"rsi": [80, 80], "price": [100, 80]}, 1,
                    FakePortfolio(position_size=10, average_entry_price=100))
    sig = evaluate_rules(rules, long_loss)
    assert sig.type is SignalType.SELL

    # long, no condition met -> HOLD
    long_calm = ctx({"rsi": [50, 50], "price": [100, 101]}, 1,
                    FakePortfolio(position_size=10, average_entry_price=100))
    assert evaluate_rules(rules, long_calm).type is SignalType.HOLD
