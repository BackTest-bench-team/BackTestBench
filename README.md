# BackTestBench

BackTestBench is a modular MVP for running deterministic, long-only trading-strategy
backtests on historical market candles. The integrated flow loads candles via a multi-broker
Data Loader (SQLite cache and chunked broker fetch), runs composable YAML strategies with
optional parameter optimization, ranks strategies and optimizer candidates, and exposes an
MVP2 Next.js dashboard with Run/Stop, per-strategy Live refresh, run progress, and Strategy
health verdicts.

Documentation status: **audited against `main` on July 19, 2026**.

## Current MVP

Implemented:

- multi-broker candle adapters via `src/broker_adapter/factory.py` — T-Bank, TwelveData,
  Bybit, Binance (tokens managed in the dashboard);
- chunked candle loading + SQLite cache (`src/data_loader/backtest_fetch.py`, `data/backtest.db`);
- composable YAML strategy engine (`src/strategy/composable/`) with series, rules, actions,
  TP/SL, constraints, time filters, trailing stop, drawdown guard, and trend filter (PR #142);
- strategy registry, plugin auto-discovery, and legacy built-in strategies (`ma_crossover`,
  `ma_rsi`, `rsi_threshold`);
- parameter optimizer — grid and random sample (`RandomSearchExecutionEngine`);
- candle-by-candle execution engine with BUY, SELL, and HOLD signals;
- long-only simulated execution with `order_size` capped at 3 lots and forced close on the
  final candle;
- commission and slippage settings in the execution engine;
- TradeLog, equity curve, final portfolio state, and analytics;
- total P&L, Sharpe ratio, max drawdown, win rate, profit factor, Calmar, period consistency,
  vs buy & hold, and 13% deposit baseline;
- Strategy health verdict (PASS / CAUTION / FAIL);
- in-memory strategy Top-N ranking (`build_top_n`) plus optimizer parameter ranking
  (`rank_optimizer_results` / `optimization.ranked[]`, PR #139);
- MVP2 Next.js dashboard with Run/Stop, multi-API token UI, bootstrap progress bar,
  per-strategy Live refresh, optimization panel, ranking, chart, and buy/sell markers;
- per-strategy **Run** checkbox (`enabled`) for the next bootstrap;
- configurable run context via `config/dashboard.json`;
- Docker Compose and a GitHub Actions PR verification workflow (three jobs on `ubuntu-latest`);
- **205** backend unit/integration tests (204 passing as of July 19; one unrelated composable
  compile test may fail on some branches).

Not implemented in the integrated MVP:

- full multi-period / walk-forward stability ranking;
- end-to-end holdout validation workflow as a dedicated second stage;
- multi-instrument portfolio UI;
- relational persistence of runs, trades, or metrics;
- the planned FastAPI service in `src/api`;
- CSV adapter behavior;
- T-Bank order placement and portfolio retrieval (`NotImplementedError`);
- scheduler, notifications, live broker order automation, or durable Top-N persistence;
- explore dock / trading-bot workflow UI (removed from dashboard).

See [Documentation status](docs/README.md) for the distinction between current
implementation, target architecture, and historical artifacts.

## Runtime Flow

```text
Browser
  -> Backtest: POST /api/config + POST /api/bootstrap
  -> Progress: GET /api/run-progress  -> data/run-progress.json
  -> Live:     POST /api/live-run + POST /api/live-run/tick  -> data/live-run.json
  -> Tokens:   GET/POST /api/tokens
  -> frontend spawns main.py (bootstrap | live-run-* | stop | refresh-ranking | …)
  -> backtest_fetch: SQLite first, broker chunks for missing ranges
  -> strategies / optimizer run on shared in-memory candles per bootstrap
  -> Analytics: metrics, strategy Top-N, optimizer ranked[], strategy health
  -> GET /api/dashboard (poll while running)
```

Runtime JSON and SQLite are the current integration bridge. They are not a durable
run-history store.

## Requirements

- Python 3.10+ for local development; Docker images currently use Python 3.12.
- Node.js 20+ and npm for the frontend.
- Docker with the Compose plugin for the integrated container workflow.
- Broker API tokens as needed (`TINKOFF_TOKEN`, `TWELVEDATA_TOKEN`, `BYBIT_TOKEN`,
  `BINANCE_TOKEN`). Bybit/Binance public klines often work without tokens.

Create the local environment file:

```bash
cp .env.example .env
```

Then set at least:

```dotenv
TINKOFF_TOKEN=your_token_here
```

Do not commit `.env` or token values. Tokens can also be saved from the dashboard UI (written
to root `.env`; in Docker Compose the file is bind-mounted from the host — see [DOCKER.md](DOCKER.md)).

## Quick Start with Docker

The default Compose service runs the integrated dashboard:

```bash
docker compose up --build
```

Open <http://localhost:3000> (or the host port from `APP_PORT`, default 80). API documentation:
<http://localhost:3000/docs>.

On first load the dashboard lists strategies from `config/strategies/*.yaml`. **Run backtest**
executes enabled strategies. **Go Live** on a strategy card refreshes one strategy on an
interval (exclusive; stops when bootstrap runs). Stop the stack with:

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
source .venv/bin/activate   # Windows: .venv\Scripts\activate
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

As of July 19, 2026:

- the backend suite contains **205 tests** (204 passing on current HEAD);
- the frontend production build targets Next.js 16;
- CI runs backend tests, frontend build, and Docker smoke on GitHub-hosted `ubuntu-latest`
  runners;
- non-blocking warnings may include `pytest-asyncio` fixture loop scope deprecation and
  Next.js workspace-root inference when multiple lockfiles are present.

## Repository Layout

```text
main.py                     CLI orchestrator (bootstrap, live-run-*, stop, …)
src/data_loader/            Candle validation, SQLite storage, backtest_fetch chunked load
src/engine/                 Simulation, portfolio, optimization
src/strategy/               Registry, plugins, composable YAML engine
src/broker_adapter/         T-Bank, TwelveData, Bybit, Binance + factory
src/analytics/              Metrics, Top-N, optimizer ranking, strategy health verdict
src/db/                     SQLAlchemy session and CandleModel (candles table only)
src/api/                    Placeholder for planned FastAPI service
frontend/                   Next.js dashboard and route handlers
config/dashboard.json       Backtest runtime settings + strategy_overrides
config/strategies/          Composable strategy YAML files
data/runtime-dashboard.json Latest bootstrap dashboard state
data/run-progress.json      Bootstrap progress (transient)
data/live-run.json          Live refresh state (transient)
data/backtest.db            SQLite candle cache (gitignored)
tests/                      Backend unit and integration tests
docs/                       Current references and target architecture
reports/                    Dated course reports and screenshots
```

## Current API

The working dashboard exposes:

- `GET /api/dashboard` — latest multi-strategy bootstrap state;
- `GET` / `POST /api/config` — load/save runtime settings and UI schema;
- `POST /api/bootstrap` — run enabled strategies (`main.py bootstrap`);
- `POST /api/stop` — stop a running backtest;
- `GET /api/run-progress` — fetch/backtest progress;
- `GET` / `POST /api/live-run` — Live refresh status / start / stop;
- `POST /api/live-run/tick` — refresh one live strategy;
- `PATCH /api/strategies/{id}` — toggle `enabled` for next bootstrap;
- `POST /api/strategies` / `DELETE /api/strategies/{id}` — add or remove composable strategies;
- `POST /api/refresh-ranking` — recompute strategy Top-N from saved metrics;
- `GET` / `POST /api/tokens` — provider token status, verify, and save.

Route details are in [docs/api_description.md](docs/api_description.md) and
[frontend/README.md](frontend/README.md). OpenAPI: [http://localhost:3000/docs](http://localhost:3000/docs)
(source: `docs/openapi.yaml`). The broader FastAPI contract in `api_description.md` is
planned, not implemented.

Removed routes (July 2026): `/api/explore`, `/api/bot`.

## Security and Financial Scope

- The project uses historical (and recent-history) market data; it does not place real orders.
- `TBankAdapter.place_order()` and `get_portfolio()` raise `NotImplementedError`.
- Results are research outputs, not financial advice or evidence of future profitability.
- `.env` on the host holds API keys in plain text when using Docker Compose bind mounts;
  see [DOCKER.md](DOCKER.md) for server guidance.
- The current T-Bank adapter defaults to disabled SSL certificate verification in the
  integrated run. This is an MVP limitation and must be changed before production use.

## Reports

- [Week 6 report](reports/Week%206%20report.md) — latest formal course weekly snapshot (July 14)
- [Week 6 report (PDF)](reports/Week%206%20report.pdf)
- [Week 5 report](reports/Week%205%20report.md)
- [Week 5 report (PDF)](reports/Week%205%20report.pdf)
- [Week 4 report](reports/Week%204%20report.md)
- [Week 3 report](reports/Week%203%20report.pdf)
- Week 1 and Week 2 PDFs are historical snapshots and intentionally retain statements that
  were true at the time.

### Optimizer ranking schema

The analytics module exposes `rank_optimizer_results()` for ranking parameter combinations
produced by the grid/random optimizer for a single strategy. This is separate from
`build_top_n()`, which ranks different strategies by Strategy health. Optimizer rows are sorted
by P&L, then drawdown, Sharpe ratio, and win rate, and are serialized as:

```json
{
  "strategy_id": "ma_rsi_composable",
  "instrument": "SBER",
  "ranked": [{ "rank": 1, "params": {}, "metrics": {} }]
}
```

The current dashboard keeps its existing `optimization.top_iterations[]` field, while also
including the canonical `optimization.ranked[]` schema for consumers.
