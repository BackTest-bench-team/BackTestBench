"""Shared parameter presets.

``config/param_presets.yaml`` maps a preset name to a list of values. A param's
``choices`` may reference one as ``preset:ma_long`` instead of repeating the
list inline; ``resolve_choices`` expands that reference."""

from __future__ import annotations

from pathlib import Path

from .errors import CompileError

DEFAULT_PRESETS_PATH = Path("config/param_presets.yaml")


def load_presets(path: str | Path = DEFAULT_PRESETS_PATH) -> dict[str, list]:
    p = Path(path)
    if not p.is_file():
        return {}
    import yaml
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise CompileError(f"presets file {p} must be a mapping")
    return data


def resolve_choices(choices, presets: dict[str, list]):
    if choices is None:
        return None
    if isinstance(choices, str):
        if not choices.startswith("preset:"):
            raise CompileError(f"choices string must be 'preset:<name>', got '{choices}'")
        key = choices.split(":", 1)[1]
        if key not in presets:
            raise CompileError(f"unknown preset '{key}'; known: {sorted(presets)}")
        return list(presets[key])
    if isinstance(choices, list):
        return list(choices)
    raise CompileError(f"choices must be a list or 'preset:<name>', got {choices!r}")
