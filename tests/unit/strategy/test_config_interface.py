"""Tests for the strategy configuration interface: schema + saved store (#94)."""

from __future__ import annotations

import json

import pytest

from src.strategy import (
    ConfigError,
    describe_all,
    describe_strategy,
    list_saved_configs,
    load_saved_config,
    delete_saved_config,
    parameter_specs,
    save_strategy_config,
)


# --- schema (what a dashboard reads to render fields) ----------------------
def test_describe_strategy_exposes_params():
    desc = describe_strategy("ma_crossover")
    assert desc["id"] == "ma_crossover"
    names = {p["name"] for p in desc["parameters"]}
    assert {"fast", "slow", "order_size"} <= names
    # each param carries enough for a form field
    fast = next(p for p in desc["parameters"] if p["name"] == "fast")
    assert fast["type"] == "int" and fast["default"] == 10


def test_describe_all_lists_every_strategy():
    ids = {d["id"] for d in describe_all()}
    assert {"ma_crossover", "rsi_threshold"} <= ids


def test_schema_is_json_serialisable():
    json.dumps(describe_all())  # must not raise


# --- saving / loading configs ----------------------------------------------
def test_save_and_load_roundtrip(tmp_path):
    path = save_strategy_config(
        "aggressive_ma",
        {"name": "ma_crossover", "instrument": "SBER", "params": {"fast": 3, "slow": 10}},
        directory=tmp_path,
    )
    assert path.is_file()
    assert "aggressive_ma" in list_saved_configs(tmp_path)

    cfg = load_saved_config("aggressive_ma", tmp_path)
    assert cfg.name == "ma_crossover"
    assert cfg.params == {"fast": 3, "slow": 10}
    assert cfg.instrument == "SBER"


def test_saving_invalid_config_is_rejected(tmp_path):
    # fast >= slow is invalid -> must not be written to disk
    with pytest.raises(Exception):
        save_strategy_config(
            "broken", {"name": "ma_crossover", "params": {"fast": 30, "slow": 10}},
            directory=tmp_path,
        )
    assert list_saved_configs(tmp_path) == []


def test_unknown_strategy_not_saved(tmp_path):
    with pytest.raises(Exception):
        save_strategy_config("x", {"name": "nope", "params": {}}, directory=tmp_path)


def test_bad_saved_name_rejected(tmp_path):
    with pytest.raises(ConfigError):
        save_strategy_config("../escape", {"name": "ma_crossover"}, directory=tmp_path)


def test_delete_saved_config(tmp_path):
    save_strategy_config("temp", {"name": "rsi_threshold"}, directory=tmp_path)
    assert delete_saved_config("temp", tmp_path) is True
    assert "temp" not in list_saved_configs(tmp_path)
