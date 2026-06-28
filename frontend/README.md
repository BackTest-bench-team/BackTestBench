# BackTestBench Frontend

Next.js 16 dashboard for running and viewing backtests. The UI reads results from a JSON file
written by the Python runner (`main.py` at the repository root). It does not run backtests
itself.

## How the pieces connect

```
Browser  →  Next.js API routes  →  spawn Python (main.py)  →  backtest + save JSON
                ↑
         poll GET /api/dashboard  ←  data/runtime-dashboard.json
```

1. The user opens `/` or changes strategy parameters.
2. The frontend calls `POST /api/bootstrap` (first load) or `POST /api/run-strategy` (param change).
3. Next.js starts `main.py` as a background process.
4. Python loads candles (database first, T-Bank API if needed), runs the engine, and writes
   `data/runtime-dashboard.json`.
5. The page polls `GET /api/dashboard` until the strategy status is `completed` or `error`.

## Folder layout

```
frontend/
├── app/
│   ├── layout.tsx          # Root HTML shell; imports global CSS
│   ├── page.tsx            # Dashboard UI (charts, params, polling)
│   ├── globals.css         # All styles (no separate CSS modules in MVP)
│   └── api/
│       ├── dashboard/route.ts    # GET — read runtime-dashboard.json
│       ├── bootstrap/route.ts    # POST — run all strategies (main.py bootstrap)
│       └── run-strategy/route.ts # POST — rerun one strategy (main.py run …)
├── lib/
│   └── spawn-python.ts     # Finds repo root, loads .env, spawns main.py
├── package.json
└── README.md                 # This file
```

### Key files outside `frontend/`

| Path | Role |
|------|------|
| `main.py` | CLI entry point: `bootstrap`, `run <strategy_id> '<params_json>'` |
| `config/dashboard.json` | Saved instrument, timeframe, capital, strategy list and default params |
| `data/runtime-dashboard.json` | Live dashboard state (gitignored; written by Python) |
| `data/backtest.db` | SQLite candle cache used by `src/data_loader` (gitignored) |
| `.env` | `TINKOFF_TOKEN` for the first candle fetch; optional `DATABASE_URL` |

## Local development

From the repository root:

```bash
cp .env.example .env
# set TINKOFF_TOKEN in .env

pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open http://localhost:3000.

The frontend resolves the repo root by walking up from `frontend/` until it finds `main.py`.
Keep the standard monorepo layout.

### Run Python manually (without the UI)

```bash
python main.py bootstrap
python main.py run ma_crossover '{"fast":15,"slow":20,"order_size":1}'
```

## API routes

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/api/dashboard` | Returns merged dashboard JSON (idle defaults if file missing) |
| `POST` | `/api/bootstrap` | Starts `python main.py bootstrap` (202 Accepted) |
| `POST` | `/api/run-strategy` | Body: `{ "strategy_id": "…", "params": { … } }` → `main.py run …` |

All run endpoints return immediately; the UI polls until results appear.

## Dashboard JSON shape (simplified)

```json
{
  "instrument": "SBER",
  "timeframe": "1h",
  "data_source": "database",
  "initial_capital": 100000,
  "strategies": [
    {
      "strategy_id": "ma_crossover",
      "status": "completed",
      "params": { "fast": 15, "slow": 20, "order_size": 1 },
      "metrics": { "total_pnl": 0, "sharpe_ratio": 0, … },
      "chart_points": [{ "date": "…", "strategy_index": 100, "benchmark_index": 100, … }],
      "trade_log": [{ "timestamp": "…", "action": "BUY", "price": 0 }]
    }
  ],
  "last_updated": "2026-06-28T12:00:00+00:00"
}
```

`data_source` is `"database"` when candles came from `DataLoader`, or `"T-Bank"` when freshly
fetched from the broker.

## Styling

All visual styles live in `app/globals.css`. There are no component-level CSS modules in the
current MVP. Charts use [Recharts](https://recharts.org/) inside `page.tsx`.

## npm scripts

```bash
npm run dev      # development server (port 3000)
npm run build    # production build
npm run start    # serve production build
npm run lint     # ESLint
```

## Known limitations

- Instrument, timeframe, and date window are configured in `config/dashboard.json`, not in the UI.
- Each strategy rerun is a separate Python subprocess.
- Only the latest dashboard state is kept; there is no run history UI.

## Verification

```bash
# Python
python -m pytest tests/integration/test_get_candles.py -v

# Frontend
npm --prefix frontend ci
npm --prefix frontend run build
```
