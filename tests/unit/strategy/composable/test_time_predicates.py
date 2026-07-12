"""Time-of-day and weekday predicates."""

from __future__ import annotations

import pytest

from src.strategy.composable import EvaluationContext, compile_predicate
from src.strategy.composable.context import StrategyState


def ctx(timestamp):
    return EvaluationContext(prices=[100], series={"price": [100]}, index=0,
                            timestamp=timestamp, portfolio=object(), state=StrategyState())


def test_time_gte():
    pred = compile_predicate({"time_gte": "17:00"}, set())
    assert pred(ctx("2025-01-02 17:05")) is True
    assert pred(ctx("2025-01-02 16:30")) is False


def test_time_lte():
    pred = compile_predicate({"time_lte": "10:00"}, set())
    assert pred(ctx("2025-01-02 09:30")) is True
    assert pred(ctx("2025-01-02 11:00")) is False


def test_time_in_range():
    pred = compile_predicate({"time_in_range": ["09:30", "17:00"]}, set())
    assert pred(ctx("2025-01-02 12:00")) is True
    assert pred(ctx("2025-01-02 18:00")) is False


def test_weekday_in():
    pred = compile_predicate({"weekday_in": [0, 1, 2, 3, 4]}, set())   # Mon-Fri
    assert pred(ctx("2025-01-06 12:00")) is True    # Monday
    assert pred(ctx("2025-01-04 12:00")) is False   # Saturday


def test_bad_time_string_rejected():
    with pytest.raises(Exception):
        compile_predicate({"time_gte": "25:99"}, set())
    with pytest.raises(Exception):
        compile_predicate({"time_gte": "5pm"}, set())
