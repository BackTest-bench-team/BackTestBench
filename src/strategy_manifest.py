"""Discover composable strategies from config/strategies/*.yaml."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from src.strategy.composable.definition import StrategyDefinition
from src.strategy.composable.strategy import register_composable_file

BASE_DIR = Path(__file__).resolve().parent.parent
STRATEGIES_DIR = BASE_DIR / "config" / "strategies"
SAFE_STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


class StrategyManifestError(ValueError):
    pass


def is_composable_yaml(data: dict[str, Any]) -> bool:
    return isinstance(data, dict) and "series" in data and "rules" in data


def default_params(definition: StrategyDefinition) -> dict[str, Any]:
    return {name: param.default for name, param in definition.params.items()}


def discover_strategy_manifests(
    directory: Path | None = None,
    *,
    register: bool = False,
) -> list[dict[str, Any]]:
    """Return strategy manifests from composable YAML files in config/strategies."""
    directory = directory or STRATEGIES_DIR
    if not directory.is_dir():
        return []

    manifests: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not is_composable_yaml(data):
            continue
        if register:
            register_composable_file(path)
        definition = StrategyDefinition.from_dict(data)
        try:
            file_ref = str(path.relative_to(BASE_DIR))
        except ValueError:
            file_ref = f"config/strategies/{path.name}"
        manifests.append(
            {
                "id": definition.name,
                "title": definition.title or definition.name,
                "file": file_ref,
                "params": default_params(definition),
            }
        )
    return manifests


def merge_strategy_params(
    manifests: list[dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Apply saved param overrides on top of YAML defaults."""
    overrides = overrides or {}
    merged: list[dict[str, Any]] = []
    for item in manifests:
        params = dict(item["params"])
        params.update(overrides.get(item["id"], {}))
        merged.append({"id": item["id"], "params": params})
    return merged


def get_strategy_overrides(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = config.get("strategy_overrides")
    if not isinstance(raw, dict):
        return {}
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}


def runtime_strategies(config: dict[str, Any]) -> list[dict[str, Any]]:
    manifests = discover_strategy_manifests(register=False)
    return merge_strategy_params(manifests, get_strategy_overrides(config))


def validate_strategy_yaml(yaml_text: str) -> StrategyDefinition:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise StrategyManifestError(f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise StrategyManifestError("Strategy YAML must be a mapping")
    if not is_composable_yaml(data):
        raise StrategyManifestError("Strategy YAML must define 'series' and 'rules'")
    definition = StrategyDefinition.from_dict(data)
    if not SAFE_STRATEGY_NAME.match(definition.name):
        raise StrategyManifestError(
            "Strategy name must be snake_case and start with a letter "
            f"(got {definition.name!r})"
        )
    return definition


def add_strategy_yaml(yaml_text: str, *, overwrite: bool = False) -> dict[str, Any]:
    """Validate composable YAML and save it under config/strategies/{name}.yaml."""
    definition = validate_strategy_yaml(yaml_text)
    STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)
    path = STRATEGIES_DIR / f"{definition.name}.yaml"
    if path.exists() and not overwrite:
        raise StrategyManifestError(f"Strategy file already exists: {path.name}")

    normalized = yaml_text if yaml_text.endswith("\n") else f"{yaml_text}\n"
    path.write_text(normalized, encoding="utf-8")
    register_composable_file(path)
    try:
        file_ref = str(path.relative_to(BASE_DIR))
    except ValueError:
        file_ref = f"config/strategies/{path.name}"
    return {
        "id": definition.name,
        "title": definition.title or definition.name,
        "file": file_ref,
        "params": default_params(definition),
    }


def delete_strategy_yaml(strategy_id: str) -> str:
    """Delete a composable strategy YAML from config/strategies/."""
    normalized = strategy_id.strip()
    if not SAFE_STRATEGY_NAME.match(normalized):
        raise StrategyManifestError(
            "Strategy id must be snake_case and start with a letter "
            f"(got {normalized!r})"
        )

    path = STRATEGIES_DIR / f"{normalized}.yaml"
    if not path.is_file():
        raise StrategyManifestError(f"Strategy file not found: {path.name}")

    path.unlink()
    return path.name
