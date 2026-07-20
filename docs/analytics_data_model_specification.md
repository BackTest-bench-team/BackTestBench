# Analytics Data Model

Last audited against `main`: **July 19, 2026**.

## Implementation Status

Implemented:

- in-memory `TradeLog`, `RunContext`, and `MetricsReport`;
- per-candle equity curve;
- metric calculation from `TradeLog + RunContext`;
- in-memory Top-N filtering/sorting helper with documented tie-breakers and partial-input handling;
- validation metrics support that reuses the same formulas as backtests;
- separate in-memory buckets for backtest metrics and validation metrics;
- ranking review entries that can show Top-N backtest rows together with latest validation metrics;
- serialization of the latest metrics into `data/runtime-dashboard.json`;
- optimization summary (top iterations per strategy) in runtime JSON when optimizer runs;
- optimizer parameter ranking via `rank_optimizer_results` / `build_optimizer_output`
  (`optimization.ranked[]` alongside `top_iterations[]`, PR #139);
- period consistency (`calculate_period_consistency`, four equal sub-periods by bar count);
- strategy health verdict (`src/analytics/strategy_verdict.py`).

Not implemented:

- relational persistence of runs, trades, equity points, metrics, or Top-N;
- atomic database replacement of Top-N;
- durable validation metrics persistence beyond job JSON files;
- frontend run-history browser;
- scheduler or live order automation.

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

1. ignores `None` reports and reports with non-finite metric values;
2. filters reports where `total_pnl > deposit_baseline_pnl` by default;
3. sorts by the ranking criterion below;
4. takes the requested `n`;
5. returns `TopNEntry` values.

The default ranking criterion (Strategy health / ``build_strategy_verdict``):

1. higher grade — PASS, then CAUTION, then FAIL;
2. fewer health flags;
3. higher ``profit_factor``;
4. higher ``vs_buy_hold_pct``;
5. higher ``consistency_pct``;
6. higher ``total_return_pct``;
7. lower ``max_drawdown``;
8. higher ``sharpe_ratio``;
9. deterministic ``strategy_id`` / ``instrument`` ordering;
10. exact duplicate ranking keys keep the original input order.

Pass ``RankingConfig.initial_capital`` when ranking from dashboard metrics (used for deposit
baseline comparison inside the verdict).

For ranking-review screens where below-baseline strategies still need to be inspected,
callers may pass `RankingConfig(require_above_baseline=False)`.

```python
@dataclass(frozen=True)
class TopNEntry:
    rank: int
    strategy_id: str
    instrument: str
    run_id: str
    total_pnl: float
    computed_at: datetime
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    deposit_baseline_pnl: float
```

`build_ranking_review()` can attach the latest validation metrics for the same
`(strategy_id, instrument)` pair to each Top-N entry. The helper is covered by unit tests
but is not called by `main.py` or displayed by the frontend.

## Validation Metrics

Validation trade logs are processed by `calculate_validation_metrics_from_trade_log()`.
The function accepts the same `TradeLog + RunContext` shape as backtest analytics and
reuses `calculate_metrics_from_trade_log()` internally. This keeps total P&L, Sharpe ratio,
max drawdown, win rate, and deposit baseline consistent between historical backtests and
second-stage validation runs.

Validation output is wrapped separately:

```python
@dataclass(frozen=True)
class ValidationMetricsReport:
    validation_run_id: str
    strategy_id: str
    instrument: str
    metrics: MetricsReport
    source_backtest_run_id: str = ""
    computed_at: datetime = datetime.now(UTC)
```

`AnalyticsResultStore` is an in-memory bridge used until durable persistence exists. It has
separate methods and buckets for `save_backtest_metrics()` and `save_validation_metrics()`,
so validation results do not overwrite historical backtest metrics. It can also return the
latest validation report per strategy/instrument for ranking review.

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

See [database_schema.md](database_schema.md). `src/db` currently persists candles only, so
the broader target run/trade/metrics schema must not be treated as implemented.

## Optimizer Result Ranking

Optimizer ranking is separate from strategy Top-N ranking. `build_top_n()` ranks different
strategies for the dashboard catalogue, while `rank_optimizer_results()` ranks parameter
combinations for one strategy after a grid/random search.

The optimizer output JSON schema is:

```json
{
  "strategy_id": "ma_rsi_composable",
  "instrument": "SBER",
  "ranked": [
    {
      "rank": 1,
      "params": { "fast": 12, "slow": 30 },
      "metrics": {
        "strategy_id": "ma_rsi_composable",
        "instrument": "SBER",
        "total_pnl": 1200.0,
        "sharpe_ratio": 1.4,
        "max_drawdown": 0.08,
        "win_rate": 0.6,
        "deposit_baseline_pnl": 250.0
      }
    }
  ]
}
```

`OptimizerRankedEntry` contains the ranked row used by this schema:

| Field | Type | Notes |
|---|---|---|
| `rank` | `int` | 1-based rank inside one optimizer run |
| `params` | `dict[str, Any]` | parameter combination evaluated by the optimizer |
| `metrics` | `MetricsReport` | metrics for this parameter combination |

`rank_optimizer_results()` accepts optimizer candidates shaped as `(params, metrics)` and
returns `list[OptimizerRankedEntry]`. It deliberately does **not** call `build_top_n()` because
optimizer rows are parameter combinations for one strategy, not separate strategies.

The ranking criterion reuses the existing analytics ordering:

1. higher `total_pnl` first;
2. then lower `max_drawdown`;
3. then higher `sharpe_ratio`;
4. then higher `win_rate`;
5. exact ties keep the input order for stable deterministic output.

Invalid optimizer rows are skipped: `None` rows, non-finite metrics such as `NaN`, and runs
explicitly marked with an empty trade log / `trade_count == 0`.

`main.py` now serializes optimizer output under each strategy's `optimization` block using
both the new canonical `ranked[]` field and the existing `top_iterations[]` field for backward
compatibility with the current dashboard UI.
