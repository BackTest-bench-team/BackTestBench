# BackTestBench

BackTestBench is a modular MVP for running deterministic, long-only trading-strategy
backtests on historical market candles. The integrated flow loads candles from SQLite or
T-Bank, runs multiple configured strategies, calculates analytics and Top-N ranking, and
displays results in a Next.js dashboard with editable parameters and benchmark comparison.

Documentation status: **audited against `main` on June 30, 2026**.

## Current MVP

Implemented:

- T-Bank historical-candle adapter for several timeframes;
- Data Loader with candle validation, SQLite upsert, and cache reuse (`data/backtest.db`);
- strategy registry, plugin auto-discovery, YAML configuration, and `ParameterSpec` schemas;
- three built-in strategies: `ma_crossover`, `ma_rsi`, `rsi_threshold`;
- candle-by-candle execution engine with BUY, SELL, and HOLD signals;
- long-only simulated execution with `order_size` capped at 3 lots and forced close on the final candle;
- TradeLog, equity curve, final portfolio state, and analytics;
- total P&L, Sharpe ratio, max drawdown, win rate, and 13% deposit baseline;
- in-memory Top-N ranking with stable tie-breakers and validation metrics support;
- Next.js multi-strategy dashboard with parameter editors, ranking panel, benchmark chart, and buy/sell markers;
- configurable run context via `config/dashboard.json` (instrument, timeframe, capital, lookback);
- Docker Compose and a self-hosted PR smoke-build workflow;
- 63 backend unit/integration tests (80% `src/` coverage).

Not implemented in the integrated MVP:

- multi-instrument UI picker (configuration path exists; picker deferred to Week 5);
- explicit Calculate/Run submit UX (parameter edits trigger immediate reruns today);
- take-profit / stop-loss and trigger/action strategy abstraction;
- parameter grid optimizer;
- relational persistence of runs, trades, or metrics;
- the planned FastAPI service in `src/api`;
- CSV adapter behavior;
- T-Bank order placement and portfolio retrieval;
- scheduler, notifications, trading bot, or durable Top-N persistence.

See [Documentation status](docs/README.md) for the distinction between current
implementation, target architecture, and historical artifacts.

## Runtime Flow

```text
Browser
  -> POST /api/config (save settings) + POST /api/bootstrap (Run backtest)
  -> frontend launches main.py bootstrap | stop | refresh-ranking | add/delete strategy
  -> strategies discovered from config/strategies/*.yaml
  -> DataLoader loads candles (SQLite cache or T-Bank fetch)
  -> each strategy emits signals on shared candle series
  -> ExecutionEngine simulates trades per strategy
  -> Analytics calculates metrics and Top-N ranking
  -> data/runtime-dashboard.json
  -> GET /api/dashboard (polled until completed)
  -> dashboard renders strategies, ranking, chart, and markers
```

The runtime JSON is the current integration bridge. It is not a durable run-history store.

## Requirements

- Python 3.10+ for local development; Docker images currently use Python 3.12.
- Node.js 20+ and npm for the frontend.
- Docker with the Compose plugin for the integrated container workflow.
- A T-Bank Invest API token for real candle downloads when the SQLite cache is empty.

Create the local environment file:

```bash
cp .env.example .env
```

Then set:

```dotenv
TINKOFF_TOKEN=your_token_here
```

Do not commit `.env` or token values.

## Quick Start with Docker

The default Compose service runs the integrated dashboard:

```bash
docker compose up --build
```

Open <http://localhost:3000>.

On first load the dashboard lists strategies from `config/strategies/*.yaml`. **Run backtest**
executes all of them. Stop the stack with:

```bash
docker compose down
```

Additional profiles:

```bash
# Backend pipeline only
docker compose --profile backend up --build backtest-app

# Backend tests
docker compose --profile test run --rm test

# Interactive Python container
docker compose --profile dev run --rm dev
```

Detailed container guidance is in [DOCKER.md](DOCKER.md).

## Local Development

Install backend dependencies and run tests:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
pytest tests -v
```

Run the pipeline directly:

```bash
python main.py bootstrap
python main.py refresh-ranking
```

Running `python main.py` without a subcommand defaults to `bootstrap`. Runtime settings live in
`config/dashboard.json`; strategy definitions live in `config/strategies/*.yaml`.

Run the frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open <http://localhost:3000>. The frontend expects the repository `data/` directory one
level above `frontend/`.

## Verification

```bash
pytest tests -q
pytest tests --cov=src --cov-report=term
npm --prefix frontend run lint
npm --prefix frontend run build
docker compose config
APP_PORT=8080 docker compose up -d --build && curl -fsS "http://localhost:8080/" && docker compose down
```

As of July 7, 2026:

- the backend suite contains **108 tests** (all passing) with **79%** coverage of `src/`;
- the frontend production build succeeds (Next.js 16);
- frontend lint reports 5 errors in `page.tsx` (non-blocking in CI until refactor);
- CI runs backend tests, frontend build, and Docker smoke on self-hosted PR checks;
- non-blocking warnings: `pytest-asyncio` fixture loop scope deprecation.

## Repository Layout

```text
main.py                     CLI orchestrator (bootstrap, stop, config-schema, add/delete strategy)
src/engine/                 Simulation, portfolio, signals, trades, run models
src/strategy/               Registry, plugin loader, ParameterSpec, built-in strategies
src/broker_adapter/         T-Bank adapter and broker-facing models
src/data_loader/            Candle validation, SQLite storage, optional in-memory cache
src/analytics/              Metrics, Top-N ranking, validation metrics
src/db/                     SQLAlchemy session and CandleModel (candles table only)
src/api/                    Placeholder for planned FastAPI service
frontend/                   Next.js dashboard and route handlers
config/dashboard.json       Runtime settings and strategy_overrides (post-optimization params)
config/strategies/          Composable strategy YAML files (dashboard discovers all *.yaml)
data/runtime-dashboard.json Latest multi-strategy dashboard state
data/backtest.db            SQLite candle cache (gitignored)
tests/                      Backend unit and integration tests
docs/                       Current references and target architecture
reports/                    Dated course reports and screenshots
```

## Current API

The working dashboard exposes:

- `GET /api/dashboard` — returns the latest multi-strategy dashboard state;
- `GET` / `POST /api/config` — load/save runtime settings and UI schema;
- `POST /api/bootstrap` — runs all strategies from `config/strategies/` (`main.py bootstrap`);
- `POST /api/stop` — stops a running backtest;
- `POST /api/strategies` / `DELETE /api/strategies/{id}` — add or remove composable strategies;
- `POST /api/refresh-ranking` — recomputes Top-N ranking from saved metrics.

Route details are in [docs/api_description.md](docs/api_description.md) and
[frontend/README.md](frontend/README.md). The broader FastAPI contract in that document is
planned, not implemented.

## Security and Financial Scope

- The project uses historical market data; it does not place real orders.
- `TBankAdapter.place_order()` and `get_portfolio()` raise `NotImplementedError`.
- Results are research outputs, not financial advice or evidence of future profitability.
- The current T-Bank adapter defaults to disabled SSL certificate verification in the
  integrated run. This is an MVP limitation and must be changed before production use.

## Reports

- [Week 4 report](reports/Week%204%20report.md) — latest course status snapshot
- [Week 3 report](reports/Week%203%20report.md)
- Week 1 and Week 2 PDFs are historical snapshots and intentionally retain statements that
  were true at the time.
