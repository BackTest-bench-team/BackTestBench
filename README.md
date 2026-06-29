# BackTestBench

BackTestBench is a modular MVP for running deterministic, long-only trading-strategy
backtests on historical market candles. The current integrated flow downloads SBER candles
from T-Bank, runs one moving-average crossover strategy, calculates analytics, and displays
the latest run in a Next.js dashboard.

Documentation status: **audited against `main` on June 23, 2026**.

## Current MVP

Implemented:

- T-Bank historical-candle adapter for several timeframes;
- strategy registry, YAML configuration parser, and parameter validation;
- one built-in `ma_crossover` strategy;
- candle-by-candle execution engine with BUY, SELL, and HOLD signals;
- long-only, all-in simulated execution and forced close on the final candle;
- TradeLog, equity curve, final portfolio state, and analytics;
- total P&L, Sharpe ratio, max drawdown, win rate, and 13% deposit baseline;
- in-memory Top-N ranking helper with stable tie-breakers;
- validation metrics support for second-stage evaluation, stored separately from backtest metrics;
- Next.js dashboard with pipeline status, metrics, chart, and **Run backtest** button;
- Docker Compose and a self-hosted PR smoke-build workflow;
- 58 backend unit/integration tests.

Not implemented in the integrated MVP:

- user-selectable strategy, instrument, timeframe, date range, or capital;
- relational persistence of runs, trades, candles, or metrics;
- the planned FastAPI service in `src/api`;
- Data Loader caching/validation in `src/data_loader`;
- CSV adapter behavior;
- T-Bank order placement and portfolio retrieval;
- scheduler, notifications, trading bot, durable Top-N persistence, or automated Top-N workflow;
- multiple-strategy/parameter comparison in the UI.

See [Documentation status](docs/README.md) for the distinction between current
implementation, target architecture, and historical artifacts.

## Runtime Flow

```text
Browser
  -> POST /api/run
  -> frontend launches main.py
  -> TBankAdapter downloads candles
  -> MACrossover emits signals
  -> ExecutionEngine simulates trades
  -> Analytics calculates metrics
  -> data/runtime-dashboard.json
  -> GET /api/dashboard
  -> dashboard renders the latest state
```

The runtime JSON is the current integration bridge. It is not a durable run-history store.

## Requirements

- Python 3.10+ for local development; Docker images currently use Python 3.12.
- Node.js 20+ and npm for the frontend.
- Docker with the Compose plugin for the integrated container workflow.
- A T-Bank Invest API token for real candle downloads.

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

The button starts `main.py` inside the full-stack container. Stop the stack with:

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
python main.py
```

This requires `TINKOFF_TOKEN`. The current run parameters are defined in `main.py`:
SBER, 1-hour candles, approximately 30 days, MA windows 15/20, and 100,000 RUB initial
capital.

Run the frontend:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open <http://localhost:3000>. The frontend expects the repository `data/` directory one
level above `frontend/`.

## Verification

```bash
pytest tests -v
npm --prefix frontend run lint
npm --prefix frontend run build
docker compose config
```

As of June 23, 2026:

- the backend suite contains 30 passing tests;
- the frontend production build passes with workspace-root and dynamic filesystem tracing
  warnings;
- frontend lint fails at `frontend/app/page.tsx:227` on
  `react-hooks/set-state-in-effect`.

## Repository Layout

```text
main.py                     Current pipeline orchestrator
src/engine/                 Simulation, portfolio, signals, trades, run models
src/strategy/               Strategy registry, config parser, MA Crossover
src/broker_adapter/         T-Bank adapter and broker-facing models
src/analytics/              Metrics, in-memory Top-N helper, validation metrics support
src/api/                    Placeholder for planned FastAPI service
src/db/                     Placeholder for planned persistence
src/data_loader/            Placeholder for planned cache/validation layer
frontend/                   Next.js dashboard and implemented route handlers
data/runtime-dashboard.json Latest dashboard state
config/strategies/          Example YAML strategy configuration
tests/                      Backend unit and integration tests
docs/                       Current references and target architecture
reports/                    Dated course reports and screenshots
```

## Current API

The working dashboard exposes:

- `POST /api/run` — launches the predefined pipeline and returns a run ID;
- `GET /api/dashboard` — returns the latest dashboard state.

The broader FastAPI contract in [docs/api_description.md](docs/api_description.md) is
planned, not implemented.

## Security and Financial Scope

- The project uses historical market data; it does not place real orders.
- `TBankAdapter.place_order()` and `get_portfolio()` raise `NotImplementedError`.
- Results are research outputs, not financial advice or evidence of future profitability.
- The current T-Bank adapter defaults to disabled SSL certificate verification in the
  integrated run. This is an MVP limitation and must be changed before production use.

## Reports

- [Week 3 report](reports/Week%203%20report.md)
- Week 1 and Week 2 PDFs are historical snapshots and intentionally retain statements that
  were true at the time.
