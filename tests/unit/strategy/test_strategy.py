"""Uses the engine dev's own types (engine.models, engine.types, engine.context,
engine.portfolio) so the strategy is exercised exactly as the engine drives it.
"""

from __future__ import annotations

import math

import pytest

from src.engine.context import ExecutionContext
from src.engine.models import Candle
from src.engine.portfolio import Portfolio
from src.engine.models import Signal
from src.engine.types import SignalType

from src.strategy import (
    ConfigError,
    ParameterValidationError,
    UnknownStrategyError,
    available_strategies,
    create_from_config,
    create_strategy,
    load_config,
    parse_config,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def candle(close: float, i: int = 0) -> Candle:
    return Candle(timestamp=str(i), open=close, high=close, low=close, close=close, volume=1.0)


def make_candles(closes: list[float]) -> list[Candle]:
    return [candle(c, i) for i, c in enumerate(closes)]


def context_at(candles: list[Candle], i: int, portfolio: Portfolio) -> ExecutionContext:
    # mirrors ExecutionEngine: historical excludes the current candle
    return ExecutionContext(
        current_candle=candles[i],
        historical_candles=candles[:i],
        portfolio=portfolio,
    )


def oscillating(n: int = 120) -> list[float]:
    return [100.0 + 10.0 * math.sin(i / 6.0) for i in range(n)]


# --------------------------------------------------------------------------- #
# registry / factory (#37)
# --------------------------------------------------------------------------- #
def test_builtin_strategy_is_registered():
    assert "ma_crossover" in available_strategies()


def test_create_strategy_by_name():
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20})
    assert strat.strategy_id == "ma_crossover"


def test_unknown_strategy_raises_clear_error():
    with pytest.raises(UnknownStrategyError) as exc:
        create_strategy("nope")
    assert "nope" in str(exc.value)


def test_create_from_config():
    cfg = parse_config({"name": "ma_crossover", "params": {"fast": 5, "slow": 20}})
    strat = create_from_config(cfg)
    assert strat.fast == 5 and strat.slow == 20


# --------------------------------------------------------------------------- #
# config parser (#38)
# --------------------------------------------------------------------------- #
def test_parse_valid_config():
    cfg = parse_config({
        "name": "ma_crossover", "instrument": "SBER", "timeframe": "1d",
        "version": "2", "params": {"fast": 5, "slow": 20},
    })
    assert (cfg.name, cfg.instrument, cfg.timeframe, cfg.version) == (
        "ma_crossover", "SBER", "1d", "2")
    assert cfg.params == {"fast": 5, "slow": 20}


def test_config_defaults():
    cfg = parse_config({"name": "ma_crossover"})
    assert cfg.params == {} and cfg.version == "1" and cfg.instrument is None


def test_config_missing_name_rejected():
    with pytest.raises(ConfigError):
        parse_config({"params": {"fast": 5}})


def test_config_bad_params_type_rejected():
    with pytest.raises(ConfigError):
        parse_config({"name": "ma_crossover", "params": [1, 2, 3]})


def test_config_bad_timeframe_rejected():
    with pytest.raises(ConfigError):
        parse_config({"name": "ma_crossover", "timeframe": "1y"})


def test_load_config_from_yaml(tmp_path):
    f = tmp_path / "cfg.yaml"
    f.write_text("name: ma_crossover\nparams:\n  fast: 5\n  slow: 20\n")
    cfg = load_config(f)
    assert cfg.name == "ma_crossover" and cfg.params["slow"] == 20


def test_load_config_missing_file_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")


# --------------------------------------------------------------------------- #
# parameter validation (#44)
# --------------------------------------------------------------------------- #
def test_fast_must_be_less_than_slow():
    with pytest.raises(ParameterValidationError) as exc:
        create_strategy("ma_crossover", {"fast": 30, "slow": 10})
    assert "fast" in str(exc.value) and "slow" in str(exc.value)


def test_negative_order_size_rejected():
    with pytest.raises(ParameterValidationError):
        create_strategy("ma_crossover", {"fast": 5, "slow": 20, "order_size": -1})


def test_order_size_above_max_rejected():
    with pytest.raises(ParameterValidationError) as exc:
        create_strategy("ma_crossover", {"fast": 5, "slow": 20, "order_size": 10})
    assert "order_size" in str(exc.value)


def test_non_integer_window_rejected():
    with pytest.raises(ParameterValidationError):
        create_strategy("ma_crossover", {"fast": 5.5, "slow": 20})


def test_strategy_cannot_start_with_broken_config():
    with pytest.raises(ParameterValidationError):
        create_strategy("ma_crossover", {"fast": 0, "slow": 20})


# --------------------------------------------------------------------------- #
# strategy behaviour (#43)
# --------------------------------------------------------------------------- #
def test_returns_valid_signals():
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20})
    candles = make_candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    for i in range(len(candles)):
        sig = strat.on_candle(context_at(candles, i, pf))
        assert isinstance(sig, Signal)
        assert isinstance(sig.type, SignalType)


def test_holds_during_warmup():
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20})
    candles = make_candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    for i in range(20):  # fewer than slow+1 closes available
        assert strat.on_candle(context_at(candles, i, pf)).type is SignalType.HOLD


def test_emits_buy_and_sell_on_oscillating_data():
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20, "order_size": 2.0})
    candles = make_candles(oscillating())
    pf = Portfolio(cash=10_000.0)
    seen = set()
    for i in range(len(candles)):
        sig = strat.on_candle(context_at(candles, i, pf))
        seen.add(sig.type)
        # toggle a fake position so BUY/SELL alternate
        if sig.type is SignalType.BUY:
            assert sig.size == 2.0
            pf.position_size = 10.0
        elif sig.type is SignalType.SELL:
            pf.position_size = 0.0
    assert SignalType.BUY in seen and SignalType.SELL in seen


def test_does_not_mutate_portfolio():
    strat = create_strategy("ma_crossover", {"fast": 5, "slow": 20})
    candles = make_candles(oscillating())
    for i in range(len(candles)):
        pf = Portfolio(cash=0.0, position_size=10.0, average_entry_price=100.0)
        before = (pf.cash, pf.position_size, pf.average_entry_price)
        strat.on_candle(context_at(candles, i, pf))
        assert (pf.cash, pf.position_size, pf.average_entry_price) == before
