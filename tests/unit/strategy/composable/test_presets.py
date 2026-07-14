"""Tests for composable parameter presets (config/param_presets.yaml)."""

from __future__ import annotations

import pytest

from src.strategy.composable.errors import CompileError
from src.strategy.composable.presets import load_presets, resolve_choices


def test_load_presets_reads_stop_loss_and_take_profit():
    presets = load_presets()
    assert presets["stop_loss_pct"] == [0.5, 0.7, 1.0, 1.5]
    assert presets["take_profit_pct"] == [0.5, 1.0, 1.5, 2.0]


def test_load_presets_reads_rsi_threshold_presets():
    presets = load_presets()
    assert presets["rsi_oversold"] == [20, 25, 30]
    assert presets["rsi_overbought"] == [60, 65, 70]
    assert presets["rsi_buy_min"] == [45, 50, 55]


def test_load_presets_missing_file_returns_empty(tmp_path):
    assert load_presets(tmp_path / "missing.yaml") == {}


def test_resolve_choices_expands_preset_reference():
    presets = {"stop_loss_pct": [0.5, 0.7, 1.0, 1.5]}
    assert resolve_choices("preset:stop_loss_pct", presets) == [0.5, 0.7, 1.0, 1.5]


def test_resolve_choices_passes_through_literal_list():
    assert resolve_choices([1, 2, 3], {}) == [1, 2, 3]


def test_resolve_choices_none_returns_none():
    assert resolve_choices(None, {}) is None


def test_resolve_choices_unknown_preset_raises():
    with pytest.raises(CompileError, match="unknown preset"):
        resolve_choices("preset:missing", {"stop_loss_pct": [0.5]})


def test_resolve_choices_invalid_string_raises():
    with pytest.raises(CompileError, match="must be 'preset:<name>'"):
        resolve_choices("not-a-preset", {})


def test_load_presets_rejects_non_mapping(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("- not-a-map\n", encoding="utf-8")
    with pytest.raises(CompileError, match="must be a mapping"):
        load_presets(path)


def test_resolve_choices_rejects_unsupported_type():
    with pytest.raises(CompileError, match="must be a list"):
        resolve_choices(123, {})
