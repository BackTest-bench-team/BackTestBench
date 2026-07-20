# BackTestBench Frontend

Next.js 16 dashboard for running and monitoring strategy backtests. The UI spawns `main.py` at
the repository root and polls JSON state written by Python.

## How it connects

```text
Browser
   ├─ Run backtest ──► POST /api/config + POST /api/bootstrap ──► main.py bootstrap
   │                                                      └──► data/runtime-dashboard.json
   ├─ Progress ──────► GET /api/run-progress ──► data/run-progress.json
   ├─ Live refresh ──► POST /api/live-run, POST /api/live-run/tick
   └─ Poll ──────────► GET /api/dashboard
```

**API docs:** [http://localhost:3000/docs](http://localhost:3000/docs) (Swagger from `docs/openapi.yaml`).

## Folder layout

```text
frontend/
├── app/
│   ├── page.tsx                     # Dashboard: cards, ranking, charts
│   ├── globals.css
│   └── api/
│       ├── bootstrap/               # POST — start bootstrap
│       ├── config/                  # GET/POST settings
│       ├── dashboard/               # GET runtime-dashboard.json
│       ├── stop/                    # POST stop backtest
│       ├── run-progress/            # GET bootstrap progress
│       ├── live-run/                # GET/POST live refresh
│       ├── live-run/tick/           # POST one live tick
│       ├── refresh-ranking/
│       ├── strategies/              # POST add YAML
│       ├── strategies/[id]/         # PATCH enabled, DELETE strategy
│       └── tokens/                  # GET/POST API keys
├── components/
│   ├── BacktestControlPanel.tsx     # Settings, data sources, Run/Stop + progress bar
│   └── AddStrategyPanel.tsx
└── lib/
    ├── spawn-python.ts
    ├── backtest-paths.ts
    └── workflow-config.ts           # Config schema helpers (shared types)
```

## Configuration

Single scope: **backtest control panel** → `config/dashboard.json` via `POST /api/config`.

- Data source: T-Bank / Twelve Data / Bybit / Binance
- Instrument, timeframe, lookback (no per-TF cap; chunked fetch + SQLite cache on backend)
- Commission / slippage, optimization mode, initial capital
- Per-strategy **Run** checkbox (`enabled`) for the next bootstrap

## Local development

```bash
pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open http://localhost:3000. The frontend finds repo root via `main.py` or `REPO_ROOT`.

### Tokens

| Variable | Provider |
|----------|----------|
| `TINKOFF_TOKEN` | T-Bank (MOEX) |
| `TWELVEDATA_TOKEN` | Twelve Data |
| `BYBIT_TOKEN` / `BINANCE_TOKEN` | Optional |

Set in root `.env` or save from the data-source card (`POST /api/tokens`). In Docker, `.env` is bind-mounted from the host.

## UI features

### Backtest control panel

- Data source cards with inline token entry
- Run backtest / Stop backtest toggle with real progress (data load → backtest strategies)
- Optimization mode (grid / sample)

### Strategy cards

- Metrics, equity chart, trade log, Strategy health (PASS/CAUTION/FAIL)
- **Go Live / Stop Live** — refreshes one strategy on an interval (exclusive; stops when bootstrap runs)
- Enable checkbox for next bootstrap run

## npm scripts

```bash
npm run dev
npm run build
npm run lint
```

## Related docs

- [`../README.md`](../README.md)
- [`../docs/api_description.md`](../docs/api_description.md)
- [`../src/data_loader/README.md`](../src/data_loader/README.md)
- [`../DOCKER.md`](../DOCKER.md)
