# BackTestBench API Reference

Last audited against `main`: **July 14, 2026** (workflow dock, multi-API tokens including
Binance, parallel trading bots, PR #144 bot pipeline, PRs #139–#146 week delta).

This document separates the API that currently works from the target FastAPI contract.

## Implementation Status

Implemented:

- Next.js route handlers on `http://localhost:3000`;
- file-backed multi-strategy state in `data/runtime-dashboard.json`;
- asynchronous launch of `main.py` subcommands from the dashboard.

Not implemented:

- the FastAPI application under `src/api` (files are empty);
- strategy/backtest/history/data REST endpoints on port 8000;
- durable run storage, request schemas, pagination, or OpenAPI generation.

## Implemented Dashboard API

### `GET /api/dashboard`

Returns the latest dashboard state. If the runtime file is missing or invalid, the route
returns a valid idle state with HTTP `200`.

The payload includes shared run context (`instrument`, `timeframe`, `initial_capital`,
`data_source`), a `strategies` array (one entry per configured strategy with status, params,
metrics, chart points, and trade log), and a `ranking` object with Top-N entries.

**Response `200` (simplified):**

```json
{
  "instrument": "SBER",
  "timeframe": "1h",
  "data_source": "database",
  "initial_capital": 100000,
  "strategies": [
    {
      "strategy_id": "ma_crossover",
      "title": "MA Crossover",
      "status": "completed",
      "params": { "fast": 12, "slow": 20, "order_size": 1 },
      "metrics": {
        "total_pnl": 28.67,
        "sharpe_ratio": 0.04,
        "max_drawdown": 0.0249,
        "win_rate": 0.5,
        "deposit_baseline_pnl": 1009.59
      },
      "chart_points": [
        { "date": "2026-06-01T10:00:00", "strategy_index": 100, "benchmark_index": 100 }
      ],
      "trade_log": [{ "timestamp": "2026-06-01T11:00:00", "action": "BUY", "price": 250.0 }]
    }
  ],
  "ranking": {
    "computed_at": "2026-06-30T10:00:00+00:00",
    "entries": [
      {
        "rank": 1,
        "strategy_id": "ma_crossover",
        "instrument": "SBER",
        "total_pnl": 28.67,
        "sharpe_ratio": 0.04,
        "max_drawdown": 0.0249,
        "win_rate": 0.5,
        "previous_rank": null,
        "rank_delta": null
      }
    ]
  },
  "last_updated": "2026-06-30T10:00:00+00:00"
}
```

Example numbers are a dated snapshot, not stable expected values.

### `POST /api/bootstrap`

Runs all composable strategies from `config/strategies/*.yaml` via `python main.py bootstrap`.
Settings (instrument, timeframe, lookback, optimization) come from `config/dashboard.json`.

**Request body:** none.

The route finds the repository root, loads `TINKOFF_TOKEN` from root `.env` or the process
environment, and launches the bootstrap subprocess.

**Response `202`:**

```json
{
  "ok": true,
  "started": true,
  "message": "Bootstrap started"
}
```

**Response `500` — token missing or launch failure:** same `ok` / `message` pattern as other
run routes.

### `GET /api/config` and `POST /api/config`

Load or save runtime settings. `GET` returns `{ settings, schema }` from `main.py config-schema`.
`POST` validates and persists instrument, timeframe, lookback, capital, and optimization options.

### `POST /api/stop`

Writes a stop request file and terminates the running `main.py bootstrap` process when possible.

### `POST /api/strategies` / `DELETE /api/strategies/{id}`

Add or remove composable strategy YAML under `config/strategies/` and sync `runtime-dashboard.json`.

### `POST /api/refresh-ranking`

Recomputes Top-N ranking from completed strategy metrics without rerunning backtests.

**Request body:** none.

Launches `python main.py refresh-ranking`.

**Response `202`:**

```json
{
  "ok": true,
  "started": true,
  "message": "Ranking refresh started"
}
```

### `GET /api/tokens` and `POST /api/tokens`

Token status per provider; verify and persist API keys for broker adapters.

### `GET /api/explore`

| Query | Action |
|-------|--------|
| (none) | Returns `explore-limits` from **dashboard config** (CLI helper; UI uses config schema instead) |
| `list=1` | List recent explore jobs |
| `job_id=` | Poll one job |

### `POST /api/explore`

Queues an explore job. Body (JSON):

```json
{
  "strategy_id": "sma_cross_demo",
  "title": "SMA Cross",
  "params": { "fast": 21, "slow": 50 },
  "initial_capital": 100000,
  "from_date": "2026-01-01",
  "to_date": "2026-03-01",
  "instrument": "SBER",
  "broker_source": "tbank"
}
```

`instrument` and `broker_source` come from the **Explore tab** pickers. If omitted, the job
falls back to `config/dashboard.json`. Spawns `main.py explore-job {job_id}` in the background.

**Response `202`:** `{ "ok": true, "job_id": "…" }`

### `DELETE /api/explore?job_id=`

Removes the job JSON file.

### `GET /api/bot`

| Query | Action |
|-------|--------|
| (none) | Returns `bot-limits` from dashboard config (legacy CLI helper) |
| `list=1` | List recent bot jobs |
| `job_id=` | Poll one job |

### `POST /api/bot`

**Start bot** (default): body includes strategy, params, and per-tab market fields:

```json
{
  "strategy_id": "ma_rsi_composable",
  "params": { "fast": 12, "slow": 50 },
  "instrument": "AAPL",
  "broker_source": "twelvedata",
  "timeframe": "1h",
  "days_to_fetch": 7,
  "use_sandbox": false,
  "initial_capital": 100000
}
```

Supported `broker_source` values match `src/broker_adapter/factory.py`:
`tbank`, `twelvedata`, `bybit`, `binance`.

**Stop:** `{ "action": "stop", "job_id": "…" }`

**Resume:** `{ "action": "resume", "job_id": "…" }` — respawns `bot-job` for a running job
after page reload.

Spawns detached `main.py bot-job {job_id}`. Multiple bots may run in parallel (separate
processes; shared SQLite candle cache).

### `DELETE /api/bot?job_id=`

Calls `bot-stop` then deletes the job file.

### Dashboard Status Values

Per-strategy status:

- `idle`;
- `running`;
- `completed`;
- `error`.

Legacy single-run pipeline fields (`run_id`, `pipeline`, `current_stage`) may appear in
older runtime files but are not the primary contract. The Week 4 `POST /api/run-strategy`
route was removed in Week 5; use `POST /api/bootstrap` to run all strategies.

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

Strategy parameter names vary by strategy; see `ParameterSpec` schemas in
`src/strategy/schema.py` and YAML files under `config/strategies/`.

## Target Error Format

When FastAPI is implemented, application errors should use:

```json
{
  "error": "Short error type",
  "detail": "Optional longer explanation"
}
```

The current Next.js routes use `ok`, `started`, and `message` fields for start responses and
embed pipeline errors in per-strategy dashboard state.

## Compatibility Work Required

Before the target API can replace the current bridge:

- implement `src/api`;
- define request/response schemas from current engine dataclasses;
- persist runs, trades, equity points, and metrics;
- replace or wrap the JSON state file;
- keep the frontend route contract backward-compatible or update the dashboard client;
- validate timezone, numeric precision, and error behavior.
