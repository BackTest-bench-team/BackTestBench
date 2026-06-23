# BackTestBench API Reference

Last audited against `main`: **June 23, 2026**.

This document separates the API that currently works from the target FastAPI contract.

## Implementation Status

Implemented:

- Next.js route handlers on `http://localhost:3000`;
- file-backed latest-run state in `data/runtime-dashboard.json`;
- asynchronous launch of the predefined pipeline.

Not implemented:

- the FastAPI application under `src/api` (files are empty);
- strategy/backtest/history/data/Top-N REST endpoints on port 8000;
- durable run storage, request schemas, pagination, or OpenAPI generation.

## Implemented Dashboard API

### `POST /api/run`

Starts the predefined `main.py` pipeline.

**Request body:** none.

The route:

1. finds the repository root;
2. loads `TINKOFF_TOKEN` from root `.env` or the process environment;
3. generates a UUID run ID;
4. initializes `data/runtime-dashboard.json`;
5. launches `main.py` as a detached process with `RUN_ID`.

**Response `202`:**

```json
{
  "ok": true,
  "started": true,
  "run_id": "5d9716da-7d18-44c8-9357-9ed47fbb5474",
  "message": "Pipeline started"
}
```

**Response `500` — token missing:**

```json
{
  "ok": false,
  "started": false,
  "message": "TINKOFF_TOKEN is missing in repository root .env"
}
```

**Response `500` — launch failure:**

```json
{
  "ok": false,
  "started": false,
  "message": "Failed to start pipeline: <reason>"
}
```

The current request is not configurable. `main.py` defines the strategy, instrument,
timeframe, date window, and capital.

### `GET /api/dashboard`

Returns the latest dashboard state. If the runtime file is missing or invalid, the route
returns a valid idle state with HTTP `200`.

**Response `200`:**

```json
{
  "run_id": "5d9716da-7d18-44c8-9357-9ed47fbb5474",
  "strategy_id": "ma_crossover",
  "strategy_version": "1",
  "instrument": "SBER",
  "timeframe": "1h",
  "data_source": "T-Bank",
  "status": "completed",
  "current_stage": "Finished",
  "pipeline": [
    {"name": "Broker Adapter", "status": "done"},
    {"name": "Strategy Module", "status": "done"},
    {"name": "Simulation Engine", "status": "done"},
    {"name": "Analytics Module", "status": "done"}
  ],
  "metrics": {
    "total_pnl": 28.67,
    "sharpe_ratio": 0.04,
    "max_drawdown": 0.0249,
    "win_rate": 0.5,
    "deposit_baseline_pnl": 1009.59
  },
  "equity_points": [
    {"date": "0", "value": 100000.0}
  ],
  "trade_count": 20,
  "final_portfolio": {
    "cash": 100028.67,
    "position_size": 0.0,
    "equity": 100028.67
  },
  "message": "Backtest completed successfully",
  "error": null,
  "last_updated": "2026-06-23T10:10:02.993903+00:00"
}
```

Example numbers are a dated snapshot, not stable expected values.

### Dashboard Status Values

Overall status:

- `idle`;
- `running`;
- `completed`;
- `error`.

Pipeline step status:

- `pending`;
- `running`;
- `done`;
- `skipped`;
- `error`.

## Target FastAPI Contract

The following routes remain planned. They are not currently callable:

| Method | Route | Planned purpose |
|---|---|---|
| `GET` | `/health` | API health check |
| `GET` | `/strategies` | List registered strategies |
| `GET` | `/strategies/{strategy_id}` | Strategy details/config |
| `POST` | `/backtest/run` | Start a configurable run |
| `GET` | `/backtest/{run_id}` | Get durable run state/results |
| `GET` | `/backtest` | List/filter run history |
| `GET` | `/top-n` | Return ranked strategies |
| `GET` | `/data/candles` | Query cached candles |

The target request for a configurable backtest is expected to include:

```json
{
  "strategy_id": "ma_crossover",
  "instrument": "SBER",
  "from_dt": "2026-05-01T00:00:00Z",
  "to_dt": "2026-06-01T00:00:00Z",
  "timeframe": "1h",
  "initial_capital": 100000.0,
  "params": {
    "fast": 10,
    "slow": 30,
    "order_size": 1.0
  }
}
```

The current strategy parameter names are `fast`, `slow`, and `order_size`; older examples
using `fast_period` and `slow_period` are obsolete.

## Target Error Format

When FastAPI is implemented, application errors should use:

```json
{
  "error": "Short error type",
  "detail": "Optional longer explanation"
}
```

The current Next.js routes instead use `ok`, `started`, and `message` fields for start
responses and embed pipeline errors in dashboard state.

## Compatibility Work Required

Before the target API can replace the current bridge:

- implement `src/api`;
- define request/response schemas from current engine dataclasses;
- persist runs, trades, equity points, and metrics;
- replace or wrap the JSON state file;
- keep the frontend route contract backward-compatible or update the dashboard client;
- validate timezone, numeric precision, and error behavior.
