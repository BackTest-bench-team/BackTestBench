# Analytics Data Model

Last audited against `main`: **June 23, 2026**.

## Implementation Status

Implemented:

- in-memory `TradeLog`, `RunContext`, and `MetricsReport`;
- per-candle equity curve;
- metric calculation from `TradeLog + RunContext`;
- in-memory Top-N filtering/sorting helper;
- serialization of the latest metrics into `data/runtime-dashboard.json`.

Not implemented:

- relational persistence of runs, trades, equity points, metrics, or Top-N;
- atomic database replacement of Top-N;
- frontend run history;
- scheduler or trading-bot consumers.

## Dependency Boundary

Analytics imports dataclasses directly from `src.engine.models`:

```python
from src.engine.models import MetricsReport, RunContext, Trade, TradeLog
```

It does not inspect execution-engine internals, but it is not independent of the engine
package at the Python import level.

## Inputs

### `Trade`

| Field | Type | Notes |
|---|---|---|
| `timestamp` | `str` | close/event timestamp |
| `entry_price` | `float` | long entry |
| `exit_price` | `Optional[float]` | populated for completed trades |
| `quantity` | `float` | executed all-in quantity |
| `pnl` | `float` | realized P&L |
| `opened_at` | `Optional[str]` | entry timestamp |
| `closed_at` | `Optional[str]` | exit timestamp |

### `TradeLog`

| Field | Type | Notes |
|---|---|---|
| `strategy_id` | `str` | strategy registry ID |
| `instrument` | `str` | run-level instrument |
| `trades` | `list[Trade]` | completed trades |
| `final_portfolio_value` | `float` | final equity |
| `equity_curve` | `list[float]` | initial capital plus one point per candle |

### `RunContext`

| Field | Type |
|---|---|
| `run_id` | `str` |
| `strategy_id` | `str` |
| `strategy_version` | `str` |
| `instrument` | `str` |
| `timeframe` | `str` |
| `period_start` | `datetime | str` |
| `period_end` | `datetime | str` |
| `initial_capital` | `float` |

## Output

### `MetricsReport`

| Field | Unit/range |
|---|---|
| `strategy_id` | identifier |
| `instrument` | identifier |
| `total_pnl` | account currency |
| `sharpe_ratio` | annualized, unbounded |
| `max_drawdown` | positive fraction |
| `win_rate` | fraction `[0, 1]` |
| `deposit_baseline_pnl` | account currency |

The dashboard formats currency as RUB, but the dataclass itself does not encode a currency.

## Top-N Helper

`build_top_n()`:

1. filters reports where `total_pnl > deposit_baseline_pnl`;
2. sorts by `total_pnl` descending;
3. takes the requested `n`;
4. returns `TopNEntry` values.

```python
@dataclass(frozen=True)
class TopNEntry:
    rank: int
    strategy_id: str
    instrument: str
    run_id: str
    total_pnl: float
    computed_at: datetime
```

The helper is covered by unit tests but is not called by `main.py` or displayed by the
frontend.

## Current Persistence

`main.py` writes the latest dashboard snapshot:

```text
data/runtime-dashboard.json
```

Writes use a temporary file followed by `os.replace`. This is atomic at file level, but it
stores one latest state only and is not the target relational model.

## Target Persistence

The planned schema includes:

- `backtest_runs`;
- `trades`;
- `equity_points`;
- `metrics`;
- `top_n`.

See [database_schema.md](database_schema.md). `src/db` is currently empty, so the target
schema must not be treated as implemented.
