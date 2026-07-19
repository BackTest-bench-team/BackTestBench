# BackTestBench API Reference

Last audited: **July 19, 2026**.

Implemented Next.js routes on `http://localhost:3000`. FastAPI under `src/api` is **not** implemented.

- **Swagger UI:** `/docs`
- **OpenAPI:** `/api/openapi` (source: `docs/openapi.yaml`)

## Dashboard

### `GET /api/dashboard`

Latest state from `data/runtime-dashboard.json` (strategies, metrics, ranking, charts).

### `POST /api/bootstrap`

1. `prepare-bootstrap` — stops Live refresh, marks backtest pending  
2. Spawns `main.py bootstrap` (202)

Settings from `config/dashboard.json`. Only strategies with `params.enabled !== false` run.

### `POST /api/stop`

Stop file + terminate bootstrap subprocess.

### `GET /api/run-progress`

Transient progress from `data/run-progress.json`:

- `phase`: `fetching` | `backtesting`
- `pct`, `label`, `current`, `total`

### `GET` / `POST /api/config`

Load/save runtime settings and UI schema (data sources, timeframes, defaults).

## Live refresh

One strategy at a time. Auto-stops when bootstrap starts.

### `GET /api/live-run`

Status via `main.py live-run-status`.

### `POST /api/live-run`

Body `{ "action": "start"|"stop", "strategy_id", "params"? }` → `live-run-start` / `live-run-stop`.

### `POST /api/live-run/tick`

Runs `live-run-tick`: reload candles (cached + incremental fetch), rerun fixed-params backtest, update dashboard card. Returns cached response if tick already running or interval not elapsed.

## Strategies

### `POST /api/strategies`

Body `{ "yaml": "..." }` — add composable strategy file.

### `PATCH /api/strategies/{id}`

Body `{ "enabled": true|false }` — include/exclude from next bootstrap.

### `DELETE /api/strategies/{id}`

Remove YAML and dashboard entry.

### `POST /api/refresh-ranking`

Recompute Top-N from saved metrics (`main.py refresh-ranking`).

## Tokens

### `GET` / `POST /api/tokens`

Status, verify, save to root `.env` (masked in GET responses).

Supported env vars: `TINKOFF_TOKEN`, `TWELVEDATA_TOKEN`, `BYBIT_TOKEN`, `BINANCE_TOKEN`.

## Strategy status values

`idle` | `running` | `completed` | `error`

## Removed routes (do not use)

- `/api/explore` — removed with Explore dock  
- `/api/bot` — removed with Trading bot dock  

## Target FastAPI contract

Planned routes (`/health`, `/backtest/run`, durable run storage) remain in `openapi.yaml` under **Planned** — not callable today.
