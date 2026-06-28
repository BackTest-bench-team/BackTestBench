# Strategy Module — Plugins & Configuration

How to add strategies (plugins) and how the configuration interface works. This
complements `strategy_module_architecture.md`; it documents the pieces added for
issues #45 (plugin loading) and #94 (configuration interface).

## Adding a strategy (plugin model)

A strategy is a plugin: a subclass of `BaseStrategy`, in its own file, that
registers itself with a decorator. Built-in strategies live in
`src/strategy/strategies/`. **Dropping a new file there is all that's needed** —
the package auto-discovers and imports every module beside it on import, so no
core file changes when a strategy is added.

```python
# src/strategy/strategies/my_strategy.py
from src.engine.models import Signal
from src.engine.types import SignalType
from ..base import BaseStrategy
from ..registry import register_strategy
from ..schema import ParameterSpec

@register_strategy("my_strategy")
class MyStrategy(BaseStrategy):
    TITLE = "My Strategy"
    PARAMS = [
        ParameterSpec("threshold", "float", 0.5, minimum=0, maximum=1,
                      description="Some threshold"),
    ]

    def validate_params(self):
        self.threshold = float(self.params.get("threshold", 0.5))

    def on_candle(self, context) -> Signal:
        return Signal(type=SignalType.HOLD)
```

That's the whole checklist: subclass `BaseStrategy`, decorate with
`@register_strategy("id")`, validate params in `validate_params`, implement
`on_candle`. The registry, the engine, and the shared contract are untouched.

### Loading plugins from outside the package

Strategies can also live outside the source tree and be loaded at runtime:

```python
from src.strategy import load_plugin_file, load_plugins_from_dir

load_plugin_file("plugins/my_strategy.py")     # one file
load_plugins_from_dir("plugins/")              # every *.py in a directory
```

Importing the file runs its `@register_strategy` decorator, so the strategy
becomes available through the normal factory — again with no change to core
code. `discover_builtin_strategies()` re-runs discovery of the built-in package
explicitly if needed.

## Configuration interface

### Parameter schema (what a dashboard renders)

Every strategy declares its editable parameters as a list of `ParameterSpec`
(`name`, `type`, `default`, optional `minimum`/`maximum`/`choices`,
`description`). The dashboard reads these to build a form — it does not need to
know anything about the strategy's internals.

```python
from src.strategy import describe_all, describe_strategy

describe_all()              # catalogue: every strategy + its parameters
describe_strategy("rsi_threshold")
# {
#   "id": "rsi_threshold",
#   "title": "RSI Threshold",
#   "description": "...",
#   "parameters": [
#       {"name": "period", "type": "int", "default": 14, "minimum": 2, ...},
#       ...
#   ]
# }
```

The output is plain JSON-serialisable dicts, so the API/frontend can return it
directly. **This module provides the data; it does not build the UI** — the
dashboard is the frontend's responsibility.

### Saving a configured strategy as a new item

A user picks a strategy, edits its parameters, and saves the result as a named
item. Saved items are small JSON files; they can be listed, loaded back, and
deleted.

```python
from src.strategy import (
    save_strategy_config, list_saved_configs, load_saved_config, delete_saved_config,
)

# save (validates the params before writing — a broken config is never saved)
save_strategy_config(
    "aggressive_ma",
    {"name": "ma_crossover", "instrument": "SBER", "params": {"fast": 3, "slow": 10}},
)

list_saved_configs()                 # ["aggressive_ma", ...]
cfg = load_saved_config("aggressive_ma")   # -> StrategyConfig, ready to run
delete_saved_config("aggressive_ma")
```

A saved item stores the strategy id, params, and instrument/timeframe/version.
Because its shape matches `parse_config`, a saved item loads straight back into
a `StrategyConfig` and runs through the engine unchanged. Saved configs default
to `config/saved_strategies/`; pass `directory=` to change it.

### End-to-end dashboard flow

```
describe_all()            ->  user sees strategies + editable parameters
(user edits params)
save_strategy_config(...)  ->  settings saved as a new named item (JSON)
list_saved_configs()       ->  user picks a saved item
load_saved_config(name)    ->  StrategyConfig -> create_from_config -> backtest
```
