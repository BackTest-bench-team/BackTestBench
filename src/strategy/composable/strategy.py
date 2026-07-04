"""ComposableStrategy — a single BaseStrategy driven entirely by config.

Registered under the id ``composable``. Given a definition (an inline dict or a
YAML file) it compiles once, then on each bar computes its series over the price
history seen so far, builds an EvaluationContext, and evaluates the rules down to
one Signal.

``register_composable_file`` registers a concrete strategy under the YAML's
``name`` (for example ``ma_rsi_composable``) with a ParameterSpec list built from
the YAML params, so ``describe_strategy(name)`` returns typed parameters with
their choices — the same shape every other strategy exposes to the dashboard."""

from __future__ import annotations

from pathlib import Path

from src.engine.models import Signal
from src.engine.types import SignalType

from ..base import BaseStrategy
from ..registry import register_strategy
from ..schema import ParameterSpec
from .compile import CompiledStrategy, compile_strategy, get_optimize_spec
from .context import EvaluationContext, StrategyState
from .definition import StrategyDefinition
from .errors import CompileError


def definition_to_specs(definition: StrategyDefinition) -> list[ParameterSpec]:
    """Map a composable definition's params onto the existing ParameterSpec."""
    return [
        ParameterSpec(
            name=p.name, type=p.type, default=p.default,
            minimum=p.minimum, maximum=p.maximum, choices=p.choices,
            optimizable=p.optimizable,
        )
        for p in definition.params.values()
    ]


@register_strategy("composable")
class ComposableStrategy(BaseStrategy):
    TITLE = "Composable (config-driven)"
    PARAMS = [ParameterSpec("file", "str", None, description="Path to a composable strategy YAML")]
    _DEFINITION: StrategyDefinition | None = None

    def __init__(self, params: dict | None = None):
        params = dict(params or {})
        definition = self._DEFINITION
        if definition is None:
            src = params.pop("definition", None)
            file = params.pop("file", None)
            if src is not None:
                definition = StrategyDefinition.from_dict(src)
            elif file is not None:
                definition = StrategyDefinition.from_yaml(file)
            else:
                raise CompileError("composable strategy requires 'definition' or 'file'")
        self.definition = definition
        self.compiled: CompiledStrategy = compile_strategy(definition, overrides=params)
        self.params = params
        self.state = StrategyState()

    def validate_params(self) -> None:  # compile already validates
        pass

    def optimize_spec(self):
        return get_optimize_spec(self.definition)

    def on_candle(self, context) -> Signal:
        closes = [c.close for c in context.historical_candles]
        closes.append(context.current_candle.close)
        series = self.compiled.compute_series(closes)
        ctx = EvaluationContext(
            prices=closes, series=series, index=len(closes) - 1,
            timestamp=getattr(context.current_candle, "timestamp", ""),
            portfolio=context.portfolio, state=self.state,
        )
        signal = self.compiled.evaluate(ctx)
        # minimal state upkeep
        self.state.bars_in_trade = self.state.bars_in_trade + 1 if ctx.is_long() else 0
        self.state.last_action = signal.type.value if hasattr(signal.type, "value") else str(signal.type)
        return signal


def register_composable_file(path: str | Path, strategy_id: str | None = None) -> str:
    """Register a composable YAML as a concrete, describable strategy."""
    definition = StrategyDefinition.from_yaml(path)
    sid = strategy_id or definition.name
    cls = type(
        f"Composable_{sid}",
        (ComposableStrategy,),
        {
            "TITLE": definition.title or sid,
            "PARAMS": definition_to_specs(definition),
            "_DEFINITION": definition,
            "__doc__": f"Composable strategy loaded from {path}",
        },
    )
    register_strategy(sid)(cls)
    return sid


def discover_composable_strategies(directory: str | Path = "config/strategies") -> list[str]:
    """Register every composable YAML (has series+rules) in a directory."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    import yaml
    registered: list[str] = []
    for f in sorted(directory.glob("*.yaml")):
        try:
            data = yaml.safe_load(f.read_text()) or {}
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and "series" in data and "rules" in data:
            registered.append(register_composable_file(f))
    return registered
