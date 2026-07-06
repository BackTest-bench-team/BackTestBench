# BackTestBench Frontend

Next.js 16 dashboard for running, ranking, and viewing strategy backtests. The UI reads results
from a JSON file written by the Python runner (`main.py` at the repository root). It does not run
backtests itself.

## How the pieces connect

```
Browser  →  Next.js API routes  →  spawn Python (main.py)  →  backtest + save JSON
                ↑
         poll GET /api/dashboard  ←  data/runtime-dashboard.json
```

1. The user opens `/` and configures run settings in the control panel.
2. **Run backtest** calls `POST /api/config` (save settings) then `POST /api/bootstrap`.
3. If saved results exist but ranking is missing, it calls `POST /api/refresh-ranking`.
4. Next.js starts `main.py` as a background process.
6. Python loads candles (database first, T-Bank API if needed), runs the engine, recomputes
   strategy ranking, and writes `data/runtime-dashboard.json`.
7. The page polls `GET /api/dashboard` until each strategy status is `completed` or `error`.

## Folder layout

```
frontend/
├── app/
│   ├── layout.tsx              # Root HTML shell; imports global CSS
│   ├── page.tsx                # Dashboard UI (ranking, search, charts, polling)
│   ├── globals.css             # Light trading-theme styles (CSS variables)
│   └── api/
│       ├── dashboard/route.ts       # GET — read runtime-dashboard.json
│       ├── bootstrap/route.ts       # POST — run all strategies (main.py bootstrap)
│       ├── config/route.ts          # GET/POST — runtime settings schema + save
│       ├── stop/route.ts            # POST — stop running backtest
│       ├── strategies/route.ts      # POST — add composable strategy YAML
│       ├── strategies/[id]/route.ts # DELETE — remove strategy YAML + dashboard state
│       └── refresh-ranking/route.ts # POST — recompute ranking only
├── components/
│   ├── BacktestControlPanel.tsx
│   └── AddStrategyPanel.tsx
├── lib/
│   ├── spawn-python.ts         # Finds repo root, loads .env, spawns main.py
│   └── backtest-paths.ts       # Paths for stop file, pid, dashboard JSON
├── package.json
└── README.md                   # This file
```

### Key files outside `frontend/`

| Path | Role |
|------|------|
| `main.py` | CLI entry point: `bootstrap`, `stop`, `config-schema`, `add-strategy`, `delete-strategy`, `refresh-ranking` |
| `src/analytics/ranking.py` | Top-N ranking via `build_top_n()` (P&L, drawdown, Sharpe, win rate) |
| `config/dashboard.json` | Runtime settings (instrument, timeframe, capital, optimization) and `strategy_overrides` |
| `config/strategies/*.yaml` | Composable strategy definitions (source of truth for which strategies run) |
| `data/runtime-dashboard.json` | Live dashboard state including ranking (gitignored) |
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
python main.py refresh-ranking
python main.py config-schema
```

## API routes

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/api/dashboard` | Returns merged dashboard JSON (idle defaults if file missing) |
| `GET` / `POST` | `/api/config` | Load/save runtime settings (`instrument`, timeframe, optimization, …) |
| `POST` | `/api/bootstrap` | Starts `python main.py bootstrap` (202 Accepted) |
| `POST` | `/api/stop` | Requests stop of a running backtest |
| `POST` | `/api/strategies` | Body: `{ yaml }` — save composable strategy to `config/strategies/` |
| `DELETE` | `/api/strategies/{id}` | Remove strategy YAML and dashboard entries |
| `POST` | `/api/refresh-ranking` | Starts `python main.py refresh-ranking` (202 Accepted) |

All run endpoints return immediately; the UI polls until results appear.

## Dashboard features

### Strategy ranking

Completed strategies are sorted best-to-worst using `build_top_n()` from `src/analytics`.
Each card shows a rank badge (`#1`, `#2`, …). When a parameter change moves a strategy up or
down, green ↑ / red ↓ indicators show the shift.

Ranking is persisted in `runtime-dashboard.json` and restored on the next page load. A full
bootstrap recalculates all strategies and ranking from scratch.

### Strategy search

The header search box accepts a strategy **title** or **ID** (partial match). Press Enter or
**Go to** to scroll the page to the matching card and highlight it briefly. Arrow keys navigate
suggestions when the dropdown is open.

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
      "title": "MA Crossover",
      "status": "completed",
      "params": { "fast": 15, "slow": 20, "order_size": 1 },
      "metrics": { "total_pnl": 0, "sharpe_ratio": 0, "max_drawdown": 0, "win_rate": 0, … },
      "chart_points": [{ "date": "…", "strategy_index": 100, "benchmark_index": 100, … }],
      "trade_log": [{ "timestamp": "…", "action": "BUY", "price": 0 }]
    }
  ],
  "ranking": {
    "computed_at": "2026-06-28T12:00:00+00:00",
    "entries": [
      {
        "rank": 1,
        "strategy_id": "ma_crossover",
        "instrument": "SBER",
        "total_pnl": 1200,
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.05,
        "win_rate": 0.55,
        "previous_rank": 2,
        "rank_delta": 1
      }
    ]
  },
  "last_updated": "2026-06-28T12:00:00+00:00"
}
```

`data_source` is `"database"` when candles came from `DataLoader`, or `"T-Bank"` when freshly
fetched from the broker.

`rank_delta` is positive when a strategy moved up (e.g. from rank 2 to rank 1).

## Styling

All visual styles live in `app/globals.css`. The UI uses a light trading-terminal theme:
blue-slate page background, soft indigo accent, tabular numerals for metrics, and minimal
shadows. There are no component-level CSS modules. Charts use [Recharts](https://recharts.org/)
inside `page.tsx`.

Design tokens are defined as CSS variables in `:root` (`--bg-page`, `--accent`, `--surface`,
etc.) for easy tuning.

## npm scripts

```bash
npm run dev      # development server (port 3000)
npm run build    # production build
npm run start    # serve production build
npm run lint     # ESLint
```

## Known limitations

- Parameter overrides after optimization are stored in `config/dashboard.json` → `strategy_overrides`.
- No take-profit / stop-loss beyond composable YAML rules; no full grid optimizer UI beyond mode/iterations/seed.
- Each strategy rerun is a separate Python subprocess.
- Only the latest dashboard state is kept; there is no run history UI.
- UI copy is English; currency values use `ru-RU` locale formatting for RUB.

## Verification

```bash
# Backend (63 tests as of June 30, 2026)
pytest tests -q

# Frontend
npm --prefix frontend ci
npm --prefix frontend run build
```
