# Strategy Module — Plugins & Configuration

How to add strategies (plugins) and how the configuration interface works. This
complements `strategy_module_architecture.md`; it documents the pieces added for
issues #45 (plugin loading) and #94 (configuration interface).

> **Week 5 note:** The MVP2 dashboard discovers **composable YAML strategies** from
> `config/strategies/*.yaml` (see `docs/strategy_composable_engine_design.md`). Plugin
> strategies below remain in the codebase and tests but are not the primary dashboard path.

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

## Constraints, time filters, and trailing stops

These features extend composable YAML strategies. All are validated or evaluated
by the composable engine; no per-strategy Python is needed.

### Parameter constraints

A `constraints:` block declares relationships between parameters that must hold.
They are checked at compile time against the resolved values, so an invalid
combination fails immediately with a clear message.

```yaml
constraints:
  - fast < slow
  - take_profit_pct > stop_loss_pct
  - take_profit_pct >= 2 * stop_loss_pct   # a risk/reward floor
```

Each entry is `term OP term`, where `OP` is one of `<  <=  >  >=  ==  !=` and a
term is a number, a parameter name, or a scaled parameter (`2 * stop_loss_pct`).
The same check is available to non-composable strategies via
`check_constraints(constraints, params)`.

### Time filters

Predicates that read the bar timestamp, useful for session rules such as forcing
a close before the market ends:

- `time_gte: "17:00"` / `time_lte: "10:00"` — compare time of day (`HH:MM`).
- `time_in_range: ["09:30", "17:00"]` — inside a daily window (wraps past midnight).
- `weekday_in: [0, 1, 2, 3, 4]` — Monday–Friday (0 = Monday).

```yaml
- id: session_close
  scope: long
  priority: 80
  when: { time_gte: "17:00" }
  then: { action: sell, size: all }
```

### Trailing stop

A trailing stop follows the price up and exits if it falls back by a set
percentage. Use the `move_stop` action to keep it updated and `trailing_stop_hit`
to exit:

```yaml
params:
  trailing_stop_pct: { type: float, default: 3, choices: [2, 3, 5, 7] }

rules:
  - id: update_trailing
    scope: long
    priority: 95
    when: { has_position: true }
    then: { action: move_stop, trailing_pct: "${trailing_stop_pct}" }

  - id: trailing_exit
    scope: long
    priority: 94
    when: { trailing_stop_hit: true }
    then: { action: sell, size: all }
```

`move_stop` ratchets the stop up to `peak * (1 - trailing_pct/100)` as the price
makes new highs (it never moves down). It is a non-terminal action: after it
updates the stop, rule evaluation continues on the same bar so a lower-priority
exit can still fire. It also keeps a single stop-loss `PositionEffect` on the
portfolio in sync, so the engine can enforce the same stop directly.

Percentages are whole numbers: `5` means 5%, not 0.05.

A complete example combining all three is
`config/strategies/ma_trailing_composable.yaml`.

## Drawdown guard and trend filter

Two more predicates, useful for the risk and trend-alignment cases raised in
review.

### Drawdown entry guard

`equity_drawdown` is true when account equity has fallen from its peak by more
than a threshold. Combine it with an entry condition to stop opening new
positions after a bad run:

```yaml
- id: entry
  scope: flat
  priority: 10
  when:
    all:
      - cross_above: [fast_ma, slow_ma]
      - not: { equity_drawdown: { gte: 50 } }   # skip entries once 50% down
  then: { action: buy, size: 1 }
```

Equity is measured as cash plus the current value of any open position, and the
peak is tracked across the whole run.

### Trend filter (`rising` / `falling`)

`rising` / `falling` test whether a series is higher / lower than it was a set
number of bars ago. Point them at a long-period series to avoid trading against
the prevailing trend:

```yaml
series:
  trend: { fn: sma, source: price, period: 100 }
rules:
  - id: entry
    scope: flat
    when:
      all:
        - cross_above: [fast_ma, slow_ma]
        - rising: [trend, 10]        # only go long while the trend is up
    then: { action: buy }
```

`rising: series` uses a one-bar lookback; `rising: [series, n]` compares against
`n` bars ago. This is a same-timeframe trend proxy; a true higher-timeframe
filter (e.g. a 1h trend while trading 5m) would need resampled data from the data
layer and is a larger follow-up.
