import pytest

from src.strategy_manifest import (
    StrategyManifestError,
    add_strategy_yaml,
    default_params,
    delete_strategy_yaml,
    discover_strategy_manifests,
    merge_strategy_params,
    validate_strategy_yaml,
)


SAMPLE_YAML = """
name: test_manifest_strategy
title: Test Manifest Strategy

params:
  order_size: { type: float, default: 1, choices: [1], optimizable: false }

series:
  fast: { fn: sma, source: price, period: 10 }
  slow: { fn: sma, source: price, period: 30 }

rules:
  - id: entry
    scope: flat
    priority: 10
    when: { cross_above: [fast, slow] }
    then: { action: buy, size: "${order_size}" }
"""


def test_validate_strategy_yaml_rejects_missing_rules():
    with pytest.raises(StrategyManifestError):
        validate_strategy_yaml("name: broken\nseries:\n  fast: { fn: sma, source: price, period: 10 }")


def test_add_and_discover_strategy_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    manifest = add_strategy_yaml(SAMPLE_YAML)
    assert manifest["id"] == "test_manifest_strategy"
    assert (tmp_path / "test_manifest_strategy.yaml").is_file()

    discovered = discover_strategy_manifests(tmp_path, register=False)
    assert len(discovered) == 1
    assert discovered[0]["id"] == "test_manifest_strategy"
    assert default_params(
        validate_strategy_yaml((tmp_path / "test_manifest_strategy.yaml").read_text(encoding="utf-8"))
    )["order_size"] == 1


def test_delete_strategy_yaml(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    add_strategy_yaml(SAMPLE_YAML)
    deleted = delete_strategy_yaml("test_manifest_strategy")
    assert deleted == "test_manifest_strategy.yaml"
    assert not (tmp_path / "test_manifest_strategy.yaml").exists()


def test_delete_strategy_yaml_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    with pytest.raises(StrategyManifestError):
        delete_strategy_yaml("missing_strategy")


def test_merge_strategy_params_applies_overrides():
    manifests = [{"id": "demo", "params": {"order_size": 1, "fast": 10}}]
    merged = merge_strategy_params(manifests, {"demo": {"fast": 12}})
    assert merged[0]["params"]["fast"] == 12
    assert merged[0]["params"]["order_size"] == 1
