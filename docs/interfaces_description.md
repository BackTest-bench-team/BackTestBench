# Current Module Contracts

Last audited against `main`: **June 23, 2026**.

The Week 2 design referred to a root-level `interfaces.py`. That file is not the current
contract source. Current runtime models are split between `src/engine`, `src/strategy`, and
`src/broker_adapter`.

## Contract Map

| Contract | Definition | Current consumer |
|---|---|---|
| Engine `Candle` | `src/engine/models.py` | strategy and execution engine |
| `Signal` / `SignalType` | `src/engine/models.py`, `src/engine/types.py` | strategy and order executor |
| `Trade`, `TradeLog`, `RunContext`, `MetricsReport` | `src/engine/models.py` | engine and analytics |
| Engine `Portfolio` | `src/engine/portfolio.py` | execution context and order executor |
| `ExecutionContext` | `src/engine/context.py` | strategy |
| `BaseStrategy` | `src/strategy/base.py` | strategy implementations |
| `BrokerAdapter` | `src/broker_adapter/base.py` | T-Bank adapter and orchestrator |
| Broker `OrderResult`, `Position`, `Portfolio` | `src/broker_adapter/models.py` | future order/portfolio operations |

The engine `Portfolio` and broker `Portfolio` are separate types.

## Engine Models

### `Candle`

```python
@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
```

The current candle does not carry `instrument` or `timeframe`; those values are supplied by
run configuration. T-Bank timestamps are converted to an ISO-like string without an explicit
timezone suffix.

### `Signal`

```python
@dataclass
class Signal:
    type: str
    size: float = 1.0
```

Strategies normally set `type` to a `SignalType` enum member:

```python
class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
```

The annotation is currently `str`, while runtime code and tests use `SignalType`. There is no
`action`, `quantity`, or `reason` field.

`size` is validated and emitted by MA Crossover, but the current all-in order executor does
not use it to calculate quantity.

### `Trade`

```python
@dataclass
class Trade:
    timestamp: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: float
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None
```

A trade is created when a long position closes. The instrument is stored at run/TradeLog
level rather than on each trade.

### `TradeLog`

```python
@dataclass
class TradeLog:
    strategy_id: str
    instrument: str
    trades: list[Trade] = field(default_factory=list)
    final_portfolio_value: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
```

`ExecutionEngine.run()` returns this object under `trade_log_report`, plus the raw trade list,
equity curve, and final portfolio.

### `RunContext`

```python
@dataclass
class RunContext:
    run_id: str
    strategy_id: str
    strategy_version: str
    instrument: str
    timeframe: str
    period_start: datetime | str
    period_end: datetime | str
    initial_capital: float
```

Analytics uses the timeframe, period, and initial capital from this context.

### `MetricsReport`

```python
@dataclass
class MetricsReport:
    strategy_id: str
    instrument: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    deposit_baseline_pnl: float
```

The integrated pipeline serializes these values into `data/runtime-dashboard.json`. It does
not currently persist them to a relational database.

### Engine `Portfolio`

```python
@dataclass
class Portfolio:
    cash: float
    position_size: float = 0.0
    average_entry_price: float = 0.0
    equity: float = 0.0
    opened_at: Optional[str] = None
```

This is a single-instrument, long-only virtual portfolio.

### `ExecutionContext`

```python
@dataclass
class ExecutionContext:
    current_candle: Candle
    historical_candles: List[Candle]
    portfolio: Portfolio
```

The strategy receives the current engine-owned portfolio object and must not mutate it.

## Strategy Contract

```python
class BaseStrategy(ABC):
    def __init__(self, params: dict): ...
    def validate_params(self) -> None: ...
    @abstractmethod
    def on_candle(self, context: ExecutionContext) -> Signal: ...
```

`on_candle` is deterministic and performs no broker, database, or file I/O.

## Broker Contract

All methods are asynchronous:

```python
await adapter.connect()
await adapter.get_candles(instrument, timeframe, from_dt, to_dt, limit=None, offset=None)
await adapter.place_order(instrument, action, quantity, price=None)
await adapter.get_portfolio(account_id=None)
await adapter.disconnect()
```

Current implementation status:

- `TBankAdapter.connect`, `disconnect`, and `get_candles` are implemented;
- `place_order` and `get_portfolio` raise `NotImplementedError`;
- `csv_adapter.py` is empty;
- `limit` truncates returned candles;
- `offset` is accepted by the interface but not used by `TBankAdapter`;
- multi-request pagination and caching are not implemented.

### Broker-facing Models

`src/broker_adapter/models.py` defines:

- `OrderResult(order_id, status, executed_price, executed_quantity, message)`;
- `Position(instrument, quantity, average_price, current_price, market_value)`;
- broker `Portfolio(account_id, cash, positions, total_value)`.

These models are not used by the current historical-data pipeline because order placement and
portfolio retrieval are not implemented.

## Current End-to-End Flow

```text
TBankAdapter.get_candles()
  -> list[engine.Candle]
  -> ExecutionEngine.run(strategy, candles, initial_capital)
  -> ExecutionContext per candle
  -> strategy.on_candle(context)
  -> Signal
  -> OrderExecutor
  -> TradeLog + equity_curve + final Portfolio
  -> calculate_metrics_from_trade_log(TradeLog, RunContext)
  -> MetricsReport
  -> runtime-dashboard.json
```

Data Loader, database persistence, FastAPI, scheduler, trading bot, and notifications are
target architecture, not part of this current flow.
