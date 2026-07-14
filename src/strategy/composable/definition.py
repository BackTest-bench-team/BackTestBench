"""The parsed YAML strategy definition.

this holds the typed ``params`` (with choices, the optimizable flag, and presets
resolved), the raw ``series`` and ``rules`` config, and the strategy name.
Turning this into something runnable happens in ``compile.py``. """

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import CompileError
from .presets import load_presets, resolve_choices

_TYPES = {"int", "float", "str", "bool"}


@dataclass
class ParamDef:
    name: str
    type: str
    default: Any
    choices: list | None = None
    optimizable: bool = False
    minimum: float | None = None
    maximum: float | None = None


@dataclass
class StrategyDefinition:
    name: str
    params: dict[str, ParamDef] = field(default_factory=dict)
    series: dict = field(default_factory=dict)
    rules: list = field(default_factory=list)
    constraints: list = field(default_factory=list)
    title: str | None = None

    @classmethod
    def from_dict(cls, data: dict, presets: dict[str, list] | None = None) -> "StrategyDefinition":
        if not isinstance(data, dict):
            raise CompileError("strategy definition must be a mapping")
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise CompileError("strategy definition needs a non-empty 'name'")
        if presets is None:
            presets = load_presets()

        params: dict[str, ParamDef] = {}
        for pname, spec in (data.get("params") or {}).items():
            if not isinstance(spec, dict) or "type" not in spec:
                raise CompileError(f"param '{pname}' must be a mapping with a 'type'")
            ptype = spec["type"]
            if ptype not in _TYPES:
                raise CompileError(f"param '{pname}' has invalid type '{ptype}'")
            choices = resolve_choices(spec.get("choices"), presets)
            optimizable = bool(spec.get("optimizable", False))
            if optimizable and not choices:
                raise CompileError(f"param '{pname}' is optimizable but has no choices")
            params[pname] = ParamDef(
                name=pname, type=ptype, default=spec.get("default"),
                choices=choices, optimizable=optimizable,
                minimum=spec.get("min"), maximum=spec.get("max"),
            )

        constraints = data.get("constraints") or []
        if not isinstance(constraints, list) or any(not isinstance(c, str) for c in constraints):
            raise CompileError("'constraints' must be a list of strings like 'fast < slow'")

        series = data.get("series") or {}
        rules = data.get("rules") or []
        if not series:
            raise CompileError("strategy definition needs a non-empty 'series'")
        if not rules:
            raise CompileError("strategy definition needs a non-empty 'rules'")
        return cls(name=name, params=params, series=series, rules=rules,
                   constraints=constraints, title=data.get("title"))

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StrategyDefinition":
        p = Path(path)
        if not p.is_file():
            raise CompileError(f"composable strategy file not found: {p}")
        import yaml
        try:
            data = yaml.safe_load(p.read_text())
        except yaml.YAMLError as exc:
            raise CompileError(f"invalid YAML in {p}: {exc}") from exc
        return cls.from_dict(data)
