# BackTestBench — API Reference

Base URL (local): `http://localhost:8000`  
All requests and responses use JSON. All timestamps are ISO 8601 UTC.

---

## Health

### `GET /health`

Check that the API is running.

**Response `200`**
```json
{
  "status": "ok"
}
```

---

## Strategies

### `GET /strategies`

List all registered strategies.

**Response `200`**
```json
[
  {
    "id": "ma_crossover",
    "name": "MA Crossover",
    "description": "Simple moving average crossover strategy.",
    "params": {
      "fast_period": 10,
      "slow_period": 30
    }
  }
]
```

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique strategy identifier, matches the YAML config filename |
| `name` | string | Human-readable name |
| `description` | string | Short description of the strategy logic |
| `params` | object | Default parameter values from the YAML config |

---

### `GET /strategies/{strategy_id}`

Get details for a single strategy.

**Path params**

| Param | Type | Description |
|---|---|---|
| `strategy_id` | string | Strategy identifier |

**Response `200`**
```json
{
  "id": "ma_crossover",
  "name": "MA Crossover",
  "description": "Simple moving average crossover strategy.",
  "params": {
    "fast_period": 10,
    "slow_period": 30
  },
  "yaml_config": "strategy:\n  name: MA Crossover\n  params:\n    fast_period: 10\n    slow_period: 30\n"
}
```

**Response `404`**
```json
{
  "error": "Strategy not found",
  "strategy_id": "unknown_strategy"
}
```

---

## Backtest

### `POST /backtest/run`

Start a new backtest run. The run executes asynchronously; poll `GET /backtest/{run_id}` for results.

**Request body**
```json
{
  "strategy_id": "ma_crossover",
  "instrument": "SBER",
  "from_dt": "2025-01-01T00:00:00Z",
  "to_dt": "2025-04-01T00:00:00Z",
  "timeframe": "1d",
  "params": {
    "fast_period": 10,
    "slow_period": 30
  }
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `strategy_id` | string | yes | ID of the strategy to run |
| `instrument` | string | yes | Ticker, e.g. `"SBER"`, `"OIL"` |
| `from_dt` | datetime | yes | Start of historical range (inclusive) |
| `to_dt` | datetime | yes | End of historical range (exclusive) |
| `timeframe` | string | yes | Candle interval: `"1m"`, `"1h"`, `"1d"` |
| `params` | object | no | Override default strategy params from YAML |

**Response `202`**
```json
{
  "run_id": "a3f7c2d1",
  "status": "pending",
  "created_at": "2026-06-15T10:00:00Z"
}
```

**Response `400`**
```json
{
  "error": "Invalid request",
  "detail": "strategy_id is required"
}
```

**Response `404`**
```json
{
  "error": "Strategy not found",
  "strategy_id": "unknown"
}
```

---

### `GET /backtest/{run_id}`

Get the status and results of a backtest run.

**Path params**

| Param | Type | Description |
|---|---|---|
| `run_id` | string | Run identifier returned by `POST /backtest/run` |

**Response `200` — run still in progress**
```json
{
  "run_id": "a3f7c2d1",
  "status": "running",
  "created_at": "2026-06-15T10:00:00Z",
  "completed_at": null,
  "trade_log": null,
  "metrics": null
}
```

**Response `200` — run completed**
```json
{
  "run_id": "a3f7c2d1",
  "status": "completed",
  "strategy_id": "ma_crossover",
  "instrument": "SBER",
  "from_dt": "2025-01-01T00:00:00Z",
  "to_dt": "2025-04-01T00:00:00Z",
  "created_at": "2026-06-15T10:00:00Z",
  "completed_at": "2026-06-15T10:00:42Z",
  "trade_log": {
    "strategy_id": "ma_crossover",
    "instrument": "SBER",
    "final_portfolio_value": 10430.5,
    "trades": [
      {
        "instrument": "SBER",
        "entry_price": 280.5,
        "exit_price": 295.0,
        "quantity": 10.0,
        "pnl": 145.0,
        "opened_at": "2025-01-15T09:30:00Z",
        "closed_at": "2025-02-03T09:30:00Z"
      }
    ]
  },
  "metrics": {
    "total_pnl": 430.5,
    "sharpe_ratio": 1.24,
    "max_drawdown": 0.07,
    "win_rate": 0.62,
    "deposit_baseline_pnl": 325.0
  }
}
```

**Response `200` — run failed**
```json
{
  "run_id": "a3f7c2d1",
  "status": "failed",
  "error": "Data Loader error: T-Bank API returned 503",
  "created_at": "2026-06-15T10:00:00Z",
  "completed_at": "2026-06-15T10:00:05Z",
  "trade_log": null,
  "metrics": null
}
```

**Response `404`**
```json
{
  "error": "Run not found",
  "run_id": "unknown"
}
```

---

### `GET /backtest`

List all backtest runs, most recent first.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `strategy_id` | string | — | Filter by strategy |
| `instrument` | string | — | Filter by instrument |
| `status` | string | — | Filter by status: `pending`, `running`, `completed`, `failed` |
| `limit` | int | 20 | Max results to return |
| `offset` | int | 0 | Pagination offset |

**Response `200`**
```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "runs": [
    {
      "run_id": "a3f7c2d1",
      "status": "completed",
      "strategy_id": "ma_crossover",
      "instrument": "SBER",
      "from_dt": "2025-01-01T00:00:00Z",
      "to_dt": "2025-04-01T00:00:00Z",
      "created_at": "2026-06-15T10:00:00Z",
      "completed_at": "2026-06-15T10:00:42Z"
    }
  ]
}
```

---

## Top-N

### `GET /top-n`

Return the current top-N ranked strategies, filtered to only those outperforming the deposit baseline.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `n` | int | 10 | Max number of strategies to return |

**Response `200`**
```json
{
  "calculated_at": "2026-06-14T02:00:00Z",
  "deposit_baseline_pnl": 325.0,
  "strategies": [
    {
      "rank": 1,
      "strategy_id": "ma_crossover",
      "instrument": "SBER",
      "total_pnl": 430.5,
      "sharpe_ratio": 1.24,
      "max_drawdown": 0.07,
      "win_rate": 0.62,
      "run_id": "a3f7c2d1"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `calculated_at` | datetime | When the top-N list was last recalculated by the Scheduler |
| `deposit_baseline_pnl` | float | P&L of a deposit at 13% annual over the same period; strategies below this are excluded |
| `rank` | int | Position in the ranking, 1 = best |

**Response `200` — no strategies above baseline**
```json
{
  "calculated_at": "2026-06-14T02:00:00Z",
  "deposit_baseline_pnl": 325.0,
  "strategies": []
}
```

---

## Data

### `GET /data/candles`

Fetch cached historical candles for an instrument and date range.

**Query params**

| Param | Type | Required | Description |
|---|---|---|---|
| `instrument` | string | yes | Ticker, e.g. `"SBER"` |
| `from_dt` | datetime | yes | Start of range (inclusive) |
| `to_dt` | datetime | yes | End of range (exclusive) |
| `timeframe` | string | yes | `"1m"`, `"1h"`, `"1d"` |

**Response `200`**
```json
{
  "instrument": "SBER",
  "timeframe": "1d",
  "from_dt": "2025-01-01T00:00:00Z",
  "to_dt": "2025-04-01T00:00:00Z",
  "count": 60,
  "candles": [
    {
      "timestamp": "2025-01-02T00:00:00Z",
      "open": 278.0,
      "high": 283.5,
      "low": 276.0,
      "close": 281.0,
      "volume": 1250000.0
    }
  ]
}
```

**Response `404`**
```json
{
  "error": "No data found",
  "instrument": "SBER",
  "timeframe": "1d",
  "from_dt": "2025-01-01T00:00:00Z",
  "to_dt": "2025-04-01T00:00:00Z"
}
```

---

## Error format

All error responses use the same structure:

```json
{
  "error": "Short error type",
  "detail": "Optional longer explanation"
}
```

| HTTP status | When |
|---|---|
| `400` | Invalid request body or query params |
| `404` | Resource not found |
| `422` | Request body schema validation failed (FastAPI default) |
| `500` | Internal server error |

---

## Run status lifecycle

```
pending → running → completed
                 → failed
```

- `pending` — run is queued, not yet started
- `running` — Simulation Engine is actively processing candles
- `completed` — TradeLog and MetricsReport are available
- `failed` — an error occurred; `error` field contains the reason