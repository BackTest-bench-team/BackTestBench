# Strategy Module Architecture

Last audited against `main`: **July 14, 2026**.

## Current Scope

The Strategy Module provides:

- a `BaseStrategy` contract;
- a registry and factory;
- plugin auto-discovery under `src/strategy/strategies/`;
- optional external plugin loading via `load_plugins_from_dir()`;
- YAML/dictionary configuration parsing;
- `ParameterSpec` schemas for dashboard parameter editors;
- strategy-specific parameter validation;
- three built-in strategies: `ma_crossover`, `ma_rsi`, `rsi_threshold`;
- composable YAML engine with constraints, time filters, trailing stop, and guards
  (`src/strategy/composable/`, PR #127 + #142);
- unit and engine-integration tests.

`main.py` loads strategies from `config/dashboard.json` and YAML files under
`config/strategies/`. The dashboard renders parameter editors from `parameter_specs` returned
by the backend; the dashboard runs all strategies via `POST /api/bootstrap`.

See also [`strategy_module_plugins_and_configuration.md`](strategy_module_plugins_and_configuration.md).

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

## Plugin Loading

Built-in strategies are discovered automatically:

```python
discover_builtin_strategies()  # imports src/strategy/strategies/*.py
load_plugin_file(path)         # single external .py plugin
load_plugins_from_dir(path)    # directory of .py plugins
```

Adding a built-in strategy requires only a new module under `src/strategy/strategies/` and
an import in `src/strategy/strategies/__init__.py` (or reliance on package discovery).

## ParameterSpec and Dashboard Integration

Each strategy declares editable parameters via `ParameterSpec` in `src/strategy/schema.py`:

```python
@dataclass(frozen=True)
class ParameterSpec:
    name: str
    type: str  # "int" | "float" | "str" | "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    choices: list[Any] | None = None
    description: str = ""
```

`describe_strategy(name)` and `describe_all()` return JSON-serialisable schemas the dashboard
uses to render forms without hardcoded per-strategy UI. Shared `order_size` is capped at
**3 lots** (`ORDER_SIZE_MAX = 3.0`) after stability testing.

## Configuration

Dashboard run context (`config/dashboard.json`):

```json
{
  "instrument": "SBER",
  "timeframe": "1h",
  "initial_capital": 100000,
  "lookback_days": 30,
  "strategies": [
    { "id": "ma_crossover", "params": { "fast": 12, "slow": 20, "order_size": 1 } }
  ]
}
```

Per-strategy YAML example (`config/strategies/ma_crossover.yaml`):

```yaml
name: ma_crossover
instrument: SBER
timeframe: 1h
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

The parser validates the envelope. Each strategy validates its own parameter values before
simulation starts.

## Built-in Strategies

### MA Crossover (`ma_crossover`)

Stateless long-only strategy from candle closes.

| Parameter | Default | Validation |
|---|---:|---|
| `fast` | `10` | integer, `>= 1`, strictly less than `slow` |
| `slow` | `30` | integer, `>= 1` |
| `order_size` | `1.0` | float, `1`–`3` lots |

Behavior: fast SMA crosses above slow while flat → BUY; crosses below while long → SELL;
otherwise HOLD.

### MA + RSI (`ma_rsi`)

Combines moving-average crossover with RSI filters for entry confirmation and overbought exit.

Key parameters: `fast`, `slow`, `rsi_period`, `rsi_buy_min`, `rsi_overbought`, `order_size`.

### RSI Threshold (`rsi_threshold`)

RSI oversold/overbought threshold strategy.

Key parameters: `period`, `oversold`, `overbought`, `order_size`.

## Execution Semantics

The current engine applies these rules after the strategy emits a signal:

- BUY is ignored if cash is non-positive or a position is already open;
- an accepted BUY uses `order_size` as lot quantity (capped at 3);
- SELL closes the entire position;
- HOLD does nothing;
- any remaining long position is force-closed on the final candle.

These rules are engine behavior, not strategy behavior.

## Reproducibility

Strategies:

- have no wall-clock reads or I/O;
- calculate from the supplied candle history;
- produce the same signal for the same context;
- do not mutate portfolio state.

Full run reproducibility in a relational store is not implemented; only the latest dashboard
JSON and SQLite candle cache persist across sessions.

## Adding a Strategy

1. Add a module under `src/strategy/strategies/`.
2. Subclass `BaseStrategy`.
3. Register a unique ID with `@register_strategy`.
4. Declare `ParameterSpec` entries for dashboard-editable fields.
5. Validate parameters in `validate_params`.
6. Implement deterministic `on_candle(context)`.
7. Add a YAML example under `config/strategies/` if needed.
8. Add contract and engine-integration tests.

## Known Gaps

- full multi-period / walk-forward stability ranking (explore window stability is partial);
- percentage-based metrics and risk/reward ratio in dashboard;
- end-to-end validation workflow (holdout second stage; analytics library + trading bot
  validation loop exist);
- multi-instrument portfolio UI (single-instrument dropdown implemented);
- signal explanations, short positions, and multi-instrument portfolios are not supported;
- relational strategy/run/parameter persistence is planned, not implemented.

## Composable Engine (Week 5+)

The dashboard discovers strategies from `config/strategies/*.yaml` with `series` and `rules`.
See `docs/strategy_composable_engine_design.md` and `src/strategy/composable/`. PR #142 added
constraints, time predicates, trailing stop, drawdown guard, and trend filter. Legacy plugin
strategies under `src/strategy/strategies/` remain in the codebase but are not the primary
dashboard path.
