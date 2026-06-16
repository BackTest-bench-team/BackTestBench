# Strategy Module — Architecture

## Overview

The Strategy Module is the component responsible for describing, registering, and
running pluggable trading strategies. It conforms to the shared `interfaces.py`
contract and never imports another module directly. The only surface the rest of
the system sees is the `BaseStrategy` abstraction: the Simulation Engine holds a
strategy instance and calls its `on_candle` method once per candle, without ever
inspecting how the strategy works internally. Everything else described here —
the registry, the configuration handling, and the plugin layout — is internal to
the module and can change freely as long as the `BaseStrategy` contract is kept.

```
                 interfaces.py  (shared, canonical)
                 ┌──────────────────────────────────┐
                 │  ActionType · Signal · Candle     │
                 │  BaseStrategy (ABC)               │
                 └──────────────────────────────────┘
                        ▲ implements             ▲ depends on
                        │                        │
   ┌────────────────────┴─────────┐    ┌─────────┴───────────┐
   │        Strategy Module        │    │  Simulation Engine  │
   │  registry · YAML · plugins    │    │    backtest loop    │
   └───────────────────────────────┘    └─────────────────────┘
       create_strategy(...) ──── strategy instance ───► on_candle(candle, portfolio)
                                                         ◄────────── Signal ─────────
```

## Scope

For MVP-1 the module provides one working built-in strategy, instantiated from a
YAML configuration, producing signals the Simulation Engine can execute. It
operates on a single instrument and is long-only. Multi-instrument support and
the validation/scheduling flows are out of scope for MVP-1, but the design does
not block them.

## The contract it implements

Every strategy implements the unified method `on_candle(candle, portfolio)`,
which receives the latest `Candle` and the current portfolio state and returns a
single `Signal`. A `Signal` carries an `action` (`ActionType.BUY`,
`ActionType.SELL`, or `ActionType.HOLD`), a `quantity` expressed as an absolute
amount in instrument units, and an optional `reason` surfaced in the trade log
for debugging.

```python
class Signal:
    action: ActionType        # BUY | SELL | HOLD
    quantity: float = 0.0     # absolute size in instrument units
    reason: str = ""          # optional, for trade-log readability

class BaseStrategy(ABC):
    def __init__(self, params: dict): ...
    def on_candle(self, candle: Candle, portfolio: dict) -> Signal: ...
```

Because every strategy exposes the same `on_candle` method with the same shape,
the Simulation Engine treats all strategies identically and never needs to know
their internals.

## Plugin model

Each strategy is an independent subclass of `BaseStrategy`, kept in its own file.
A strategy holds whatever indicator state it needs — moving-average buffers,
counters, previous values — as internal attributes set up when it is created. It
is pure computation over the candles it is fed and the portfolio it is handed; it
never touches the database, the broker, or any other module.

## Registry and factory

The module keeps a registry mapping a strategy name to its class. A strategy
registers itself by name when its file is loaded, so adding one is purely
additive and the rest of the module is never edited.

```python
@register_strategy("sma_crossover")
class SmaCrossover(BaseStrategy):
    ...

create_strategy(name: str, params: dict) -> BaseStrategy
available_strategies() -> list[str]
```

The factory `create_strategy` turns a stored or loaded configuration into a live
instance by looking up the requested name and constructing the matching strategy
from its parameters. Requesting a name that was never registered fails with a
clear error rather than silently doing nothing.

## Configuration

A strategy is described by a YAML configuration: which strategy to use, the
instrument and timeframe it trades, a version label, and a block of
strategy-specific parameters such as indicator periods, thresholds, and order
size.

```yaml
name: sma_crossover
instrument: SBER
timeframe: 1m
version: "1"
params:
  fast: 10
  slow: 30
  order_size: 1.0
```

The module parses the YAML into the plain `params` dictionary and hands it to the
strategy at construction. The envelope fields (`name`, `instrument`,
`timeframe`, `version`) are used by the module and the engine; the `params` block
is opaque to the core and validated by the individual strategy itself. A strategy
validates its parameters when created and fails fast on bad input, so a
misconfigured strategy is rejected before it ever reaches the simulation loop.

## Lifecycle and reproducibility

The Simulation Engine drives the lifecycle: it creates a strategy from its
configuration, then feeds candles to `on_candle` one at a time in ascending time
order.

```python
strategy = create_strategy(name, params)
for candle in candles:
    signal = strategy.on_candle(candle, portfolio)
```

Reproducibility rests on three rules. A fresh strategy instance is created for
each run, so there is no leftover state and no separate reset step is needed.
`on_candle` is deterministic — no wall-clock reads, no unseeded randomness, no
input or output — so the same configuration and candle sequence always produce
the same signals. The `version` and `params` that produced a run are stored
alongside its results, so any run can be reproduced later.

## Signal semantics

A strategy returns exactly one signal per candle and never returns nothing; to
take no action it returns a `HOLD`. The `quantity` is an absolute amount in
instrument units, normally derived from the strategy's own parameters. For MVP-1,
which is long-only, a `BUY` opens or increases a long position, a `SELL` reduces
or closes it, and a `HOLD` does nothing. The strategy reads the portfolio to
inform its decisions — for example, only selling when it currently holds a
position — but never modifies it, because the engine owns all portfolio state and
execution. Until a strategy has seen enough candles to compute its indicators, it
returns hold signals; this warmup period is handled inside the strategy and
produces no trades.

## Extensibility

Adding a new strategy means creating a new file, subclassing `BaseStrategy`,
registering it under a name, validating its parameters on construction, and
implementing `on_candle`. No change to the platform core is required at any step.
New strategies do not touch the registry, the engine, or the shared contract, and
the analytics side can grow its list of metrics independently of the strategies.

## Contract tests

A reusable test harness checks that any strategy obeys the contract the engine
depends on. It feeds a synthetic candle series through a strategy and verifies
that every call returns a valid `Signal`, that the strategy does not modify the
portfolio it is given, that running the same candles through a freshly created
instance twice yields an identical sequence of signals, that only hold signals
are produced during warmup, and that the registry can create a registered
strategy while an unknown name raises an error. A simple reference strategy exists
so these checks have something concrete to run against and so the rest of the
system has a worked example of the contract in use.

## Open coordination points

A few details depend on agreement with neighbouring parts of the system. The
exact shape of the `portfolio` dictionary passed into `on_candle` needs to be
fixed with whoever builds the Simulation Engine, since strategies read it to check
their current position and available cash; a minimal shape exposing `cash` and
per-instrument `positions` (with `quantity` and `avg_price`) is enough for MVP-1.
Responsibility for enforcing hard risk limits should also be settled: the intended
split is that a strategy expresses intent through its signal while the engine
enforces limits such as maximum position size. Finally, position sizing in MVP-1
is taken from the strategy's own parameters, with portfolio-aware sizing left as a
later enhancement.
