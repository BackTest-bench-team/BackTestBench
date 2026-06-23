# Strategy Module Architecture

Last audited against `main`: **June 23, 2026**.

## Current Scope

The Strategy Module provides:

- a `BaseStrategy` contract;
- a registry and factory;
- YAML/dictionary configuration parsing;
- strategy-specific parameter validation;
- one built-in `ma_crossover` strategy;
- unit and engine-integration tests.

The integrated dashboard still constructs `MACrossover` directly in `main.py`; it does not
load `config/strategies/ma_crossover.yaml` or expose strategy selection in the UI.

## Runtime Contract

```python
class BaseStrategy(ABC):
    def __init__(self, params: dict):
        self.params = params
        self.validate_params()

    def validate_params(self) -> None:
        ...

    @abstractmethod
    def on_candle(self, context: ExecutionContext) -> Signal:
        ...
```

`ExecutionContext` contains:

- `current_candle`;
- all `historical_candles` before the current candle;
- the engine-owned single-instrument `Portfolio`.

The strategy must return exactly one `Signal` and must not mutate the context or portfolio.

```python
Signal(type=SignalType.BUY | SignalType.SELL | SignalType.HOLD, size=1.0)
```

There is no `reason` field in the current signal model.

## Registry and Factory

Strategies register through a class decorator:

```python
@register_strategy("ma_crossover")
class MACrossover(BaseStrategy):
    ...
```

Public functions:

```python
available_strategies() -> list[str]
get_strategy_class(name) -> type[BaseStrategy]
create_strategy(name, params=None) -> BaseStrategy
create_from_config(config) -> BaseStrategy
```

An unknown name raises `UnknownStrategyError`. Duplicate registration under a different
class raises `ValueError`.

## Configuration

Current schema:

```yaml
name: ma_crossover
instrument: SBER
timeframe: 1m
version: "1"
params:
  fast: 10
  slow: 30
  order_size: 1.0
```

`StrategyConfig` fields:

- `name`: required non-empty strategy ID;
- `instrument`: optional string;
- `timeframe`: optional, one of `1m`, `5m`, `15m`, `1h`, `4h`, `1d`;
- `version`: string, default `"1"`;
- `params`: dictionary, default `{}`.

The parser validates the envelope. Each strategy validates its own parameter values.

## MA Crossover

`MACrossover` is a stateless long-only strategy calculated from candle closes.

Parameters:

| Name | Default | Validation |
|---|---:|---|
| `fast` | `10` | integer, `>= 1`, strictly less than `slow` |
| `slow` | `30` | integer, `>= 1` |
| `order_size` | `1.0` | numeric, `> 0` |

Behavior:

- fewer than `slow + 1` closes: HOLD;
- fast SMA crosses above slow SMA while flat: BUY;
- fast SMA crosses below slow SMA while long: SELL;
- otherwise: HOLD.

The strategy reads `context.portfolio.position_size` to avoid repeated BUY while long and
SELL while flat.

## Execution Semantics

The current engine is more restrictive than the strategy signal:

- BUY is ignored if cash is non-positive or a position is already open;
- an accepted BUY invests all available cash;
- `Signal.size` does not currently affect executed quantity;
- SELL closes the entire position;
- HOLD does nothing;
- any remaining long position is force-closed on the final candle.

These rules are engine behavior, not strategy behavior.

## Reproducibility

The MA strategy:

- has no wall-clock reads or I/O;
- calculates from the supplied candle history;
- produces the same signal for the same context;
- does not mutate portfolio state.

The integrated run does not yet persist full strategy parameters and input candles in a
relational run record, so durable reproducibility is incomplete.

## Adding a Strategy

1. Add a module under `src/strategy/strategies/`.
2. Subclass `BaseStrategy`.
3. Register a unique ID with `@register_strategy`.
4. Validate parameters in `validate_params`.
5. Implement deterministic `on_candle(context)`.
6. Import the module from `src/strategy/strategies/__init__.py` so registration occurs.
7. Add contract and engine-integration tests.

## Known Gaps

- only one strategy is implemented;
- the dashboard does not select strategies or parameters;
- the example YAML is not used by `main.py`;
- `order_size` is ignored by all-in execution;
- signal explanations, stop-loss, take-profit, scaling, short positions, and
  multi-instrument portfolios are not supported;
- strategy/version/parameter persistence is planned, not implemented.
