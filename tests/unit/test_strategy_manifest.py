import pytest

from src.strategy_manifest import (
    StrategyManifestError,
    add_strategy_yaml,
    default_params,
    delete_strategy_yaml,
    discover_strategy_manifests,
    get_strategy_overrides,
    merge_strategy_params,
    runtime_strategies,
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


def test_validate_strategy_yaml_rejects_invalid_yaml_and_name():
    with pytest.raises(StrategyManifestError, match="Invalid YAML"):
        validate_strategy_yaml("name: [")
    with pytest.raises(StrategyManifestError, match="must be a mapping"):
        validate_strategy_yaml("- not a mapping")
    with pytest.raises(StrategyManifestError, match="series"):
        validate_strategy_yaml("name: plain\nparams: {}")
    with pytest.raises(StrategyManifestError, match="snake_case"):
        validate_strategy_yaml(SAMPLE_YAML.replace("test_manifest_strategy", "Bad-Name"))


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


def test_add_strategy_yaml_rejects_duplicate_without_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    add_strategy_yaml(SAMPLE_YAML)
    with pytest.raises(StrategyManifestError, match="already exists"):
        add_strategy_yaml(SAMPLE_YAML)
    updated = add_strategy_yaml(SAMPLE_YAML.replace("Test Manifest Strategy", "Updated"), overwrite=True)
    assert updated["title"] == "Updated"


def test_discover_skips_invalid_and_non_composable_files(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    (tmp_path / "broken.yaml").write_text("name: [", encoding="utf-8")
    (tmp_path / "legacy.yaml").write_text("name: legacy\nparams: {}\n", encoding="utf-8")
    (tmp_path / "test_manifest_strategy.yaml").write_text(SAMPLE_YAML, encoding="utf-8")
    assert len(discover_strategy_manifests(tmp_path, register=False)) == 1


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


def test_delete_strategy_yaml_rejects_invalid_id(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    with pytest.raises(StrategyManifestError, match="snake_case"):
        delete_strategy_yaml("Bad-Name")


def test_merge_strategy_params_applies_overrides():
    manifests = [{"id": "demo", "params": {"order_size": 1, "fast": 10}}]
    merged = merge_strategy_params(manifests, {"demo": {"fast": 12}})
    assert merged[0]["params"]["fast"] == 12
    assert merged[0]["params"]["order_size"] == 1


def test_get_strategy_overrides_ignores_invalid_entries():
    assert get_strategy_overrides({"strategy_overrides": "bad"}) == {}
    assert get_strategy_overrides({"strategy_overrides": {"demo": {"fast": 12}, "skip": "x"}}) == {
        "demo": {"fast": 12}
    }


def test_runtime_strategies_merges_config_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr("src.strategy_manifest.STRATEGIES_DIR", tmp_path)
    add_strategy_yaml(SAMPLE_YAML)
    strategies = runtime_strategies(
        {"strategy_overrides": {"test_manifest_strategy": {"order_size": 2}}}
    )
    assert strategies[0]["id"] == "test_manifest_strategy"
    assert strategies[0]["params"]["order_size"] == 2
