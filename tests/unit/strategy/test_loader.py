"""Tests for plugin loading and discovery (issue #45)."""

from __future__ import annotations

import textwrap

from src.strategy import (
    available_strategies,
    discover_builtin_strategies,
    load_plugin_file,
)


def test_builtins_discovered_automatically():
    # importing the package already ran discovery
    ids = available_strategies()
    assert "ma_crossover" in ids and "rsi_threshold" in ids


def test_discover_is_idempotent():
    before = set(available_strategies())
    after = set(discover_builtin_strategies())
    assert before <= after  # discovery never drops registrations


def test_external_plugin_loaded_without_touching_core(tmp_path):
    """A strategy in an arbitrary file registers itself when loaded — no edit
    to any module in src/strategy is required."""
    plugin = tmp_path / "always_hold.py"
    plugin.write_text(textwrap.dedent('''
        from src.engine.models import Signal
        from src.engine.types import SignalType
        from src.strategy.base import BaseStrategy
        from src.strategy.registry import register_strategy

        @register_strategy("always_hold")
        class AlwaysHold(BaseStrategy):
            def on_candle(self, context):
                return Signal(type=SignalType.HOLD)
    '''))

    assert "always_hold" not in available_strategies()
    load_plugin_file(plugin)
    assert "always_hold" in available_strategies()
