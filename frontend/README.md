# BackTestBench Frontend

Next.js 16 dashboard for running, ranking, exploring, and validating strategy backtests. The UI
does not run the engine itself — it spawns `main.py` at the repository root and polls JSON job
files written by Python.

## How the pieces connect

```text
Browser
   │
   ├─ Run backtest ──► POST /api/config + POST /api/bootstrap ──► main.py bootstrap
   │                                                      └──► data/runtime-dashboard.json
   │
   ├─ Explore ───────► POST /api/explore ──► main.py explore-start / explore-job
   │                                                      └──► data/explore-jobs/*.json
   │
   ├─ Trading Bot ───► POST /api/bot ──────► main.py bot-start / bot-job
   │                                                      └──► data/bot-jobs/*.json
   │
   └─ Poll results ──► GET /api/dashboard | /api/explore?job_id=… | /api/bot?job_id=…
```

1. **Backtest control panel** saves runtime settings to `config/dashboard.json` and starts
   `main.py bootstrap`.
2. **Explore** and **Trading Bot** live in the bottom **Workflow dock** as independent tabs with
   their own API/instrument pickers (not tied to the backtest settings after open).
3. Python loads candles via `DataLoader`, runs strategies/optimizer, and writes results under
   `data/`.

## Folder layout

```text
frontend/
├── AGENTS.md                        # Cursor/Next.js agent rules (keep)
├── app/
│   ├── layout.tsx
│   ├── page.tsx                     # Main dashboard: ranking, cards, workflow dock
│   ├── globals.css                  # Light trading-terminal theme (CSS variables)
│   └── api/
│       ├── bootstrap/route.ts       # POST — run all strategies
│       ├── config/route.ts          # GET/POST — runtime settings schema + save
│       ├── dashboard/route.ts       # GET — runtime-dashboard.json
│       ├── stop/route.ts            # POST — stop running backtest
│       ├── refresh-ranking/route.ts # POST — recompute ranking only
│       ├── strategies/route.ts      # POST — add composable strategy YAML
│       ├── strategies/[id]/route.ts # DELETE — remove strategy
│       ├── tokens/route.ts          # GET/POST — token status + verify/save
│       ├── explore/route.ts         # GET/POST/DELETE — explore jobs
│       └── bot/route.ts             # GET/POST/DELETE — trading bot jobs
├── components/
│   ├── BacktestControlPanel.tsx     # Backtest settings, data source cards, API tokens
│   ├── AddStrategyPanel.tsx         # Paste/upload composable strategy YAML
│   ├── ExploreDock.tsx              # Explore session panel (date range + stability)
│   ├── BotDock.tsx                  # Trading bot panel (rolling validation loop)
│   ├── WorkflowDock.tsx             # Tabbed shell: Explore | Trading Bot
│   └── WorkflowMarketPicker.tsx     # Shared data source + instrument selects
└── lib/
    ├── spawn-python.ts              # Find repo root, spawn main.py with env
    ├── backtest-paths.ts            # Paths to dashboard JSON, stop/pid files
    ├── env-file.ts                  # Optional local .env merge for dev
    ├── session-fingerprint.ts       # Dedupe explore/bot tabs after reload
    └── workflow-config.ts           # Config schema, per-workflow market defaults
```

### Key files outside `frontend/`

| Path | Role |
|------|------|
| `main.py` | CLI: `bootstrap`, `explore-*`, `bot-*`, `config-schema`, … |
| `config/dashboard.json` | **Backtest-only** runtime settings + `strategy_overrides` |
| `config/strategies/*.yaml` | Composable strategy definitions |
| `data/runtime-dashboard.json` | Bootstrap results + ranking (gitignored) |
| `data/explore-jobs/*.json` | Explore job state (gitignored) |
| `data/bot-jobs/*.json` | Trading bot job state (gitignored) |
| `data/backtest.db` | Shared SQLite candle cache (gitignored) |
| `src/engine/trading_bot.py` | PR #144 validation loop |
| `src/data_loader/README.md` | Broker → loader → engine pipeline |

## Configuration scopes

Three separate configuration layers — they do not overwrite each other:

| Scope | Controls | Storage |
|-------|----------|---------|
| **Backtest control** | Instrument, timeframe, lookback, optimization for `bootstrap` | `config/dashboard.json` via `POST /api/config` |
| **Explore tab** | Data source, instrument, date range for one parameter set | Per-session state + `localStorage` |
| **Trading Bot tab** | Data source, instrument, rolling window, sandbox flag | Per-session state + `localStorage` |

**Priority:** backtest settings always apply only to **Run backtest**. Explore and Trading Bot
use `WorkflowMarketPicker` and remember the last workflow choice in
`localStorage` key `backtestbench.workflow.market.v1`. Changing backtest API/instrument does
not change open explore/bot tabs.

Instrument lists are filtered per data source (MOEX tickers for T-Bank, global equities for
Twelve Data, crypto for Bybit) using the same schema as `GET /api/config`.

## Local development

From the repository root:

```bash
pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open http://localhost:3000.

The frontend walks up from `frontend/` until it finds `main.py`, or uses `REPO_ROOT` if set.

### Environment variables / API tokens

Python child processes receive `process.env` plus optional values from a local `.env` file
(development only). In CI/Docker, set tokens as environment variables:

| Variable | Provider |
|----------|----------|
| `TINKOFF_TOKEN` | T-Bank (MOEX) |
| `TWELVEDATA_TOKEN` | Twelve Data |
| `BYBIT_TOKEN` | Bybit (optional; public klines often work without it) |

Token entry is on the **backtest** data-source cards (`POST /api/tokens`). Workflow tabs reuse
those credentials when fetching candles.

### Run Python manually

```bash
python main.py bootstrap
python main.py config-schema
python main.py explore-start '{"strategy_id":"sma_cross_demo",…}'
python main.py bot-limits
```

## API routes

| Method | Path | Action |
|--------|------|--------|
| `GET` | `/api/dashboard` | Read `runtime-dashboard.json` |
| `GET` / `POST` | `/api/config` | Load/save **backtest** settings + UI schema |
| `POST` | `/api/bootstrap` | Start `main.py bootstrap` (202) |
| `POST` | `/api/stop` | Request backtest stop |
| `POST` | `/api/refresh-ranking` | Recompute ranking only (202) |
| `POST` | `/api/strategies` | Body `{ yaml }` — add composable strategy |
| `DELETE` | `/api/strategies/{id}` | Remove strategy YAML + dashboard state |
| `GET` / `POST` | `/api/tokens` | Token status; verify/save tokens |
| `GET` | `/api/explore?list=1` | List explore jobs |
| `GET` | `/api/explore?job_id=` | Poll one explore job |
| `POST` | `/api/explore` | Start explore (`instrument`, `broker_source`, dates, params) |
| `DELETE` | `/api/explore?job_id=` | Delete explore job file |
| `GET` | `/api/bot?list=1` | List bot jobs |
| `GET` | `/api/bot?job_id=` | Poll one bot job |
| `GET` | `/api/bot` | CLI helper: `bot-limits` from dashboard config |
| `POST` | `/api/bot` | Start/stop/resume bot (`action`, `job_id`, market fields) |
| `DELETE` | `/api/bot?job_id=` | Stop + delete bot job |

Long-running routes return **202 Accepted** immediately; the UI polls job endpoints every ~1.5–2s
until `completed`, `stopped`, or `error`.

## UI features

### Backtest control panel

- **Data source** — T-Bank / Twelve Data / Bybit cards with inline API token on the selected
  provider.
- **Instrument / timeframe / lookback** — for the main bootstrap run only.
- **Optimization** — mode and iteration count; Top-5 table on each strategy card.

### Strategy cards

- Rank badge, P&L / Sharpe / drawdown / win rate, equity chart (Recharts), trade log.
- **Explore** and **Trading Bot** on the card and on each Top-5 parameter row.

### Workflow dock (bottom panel)

Unified tab strip; collapsible. Modes: **Explore** (`EXP`) and **Trading Bot** (`BOT`).

- Multiple tabs per mode (deduped by strategy + params + market fingerprint).
- Tabs restore after reload from `localStorage` + server job list.
- Each tab has its own **Data source** and **Instrument** dropdowns (`WorkflowMarketPicker`).

### Explore panel

- Daily candles (`1d`); date range bounded by broker lookback for the tab's data source.
- Sends `instrument` + `broker_source` with the job payload (not dashboard config).
- Stability metrics after the run completes.

### Trading Bot panel

- Rolling window in days; optional T-Bank sandbox host for candle fetches.
- Each tick: `force_fetch=True` → `MinimalTradingBot.run_validation()` → live chart update.
- **Stop bot** sets job status `stopped`; orders are simulated only.
- When **two or more** bots are running, a short notice appears: they share `data/backtest.db`.
- Each bot runs in a separate Python subprocess with its own `BrokerAdapter`.

### Strategy search

Header search by title or ID; Enter scrolls to the card and highlights it briefly.

## Session persistence

| Storage | Key | Content |
|---------|-----|---------|
| `localStorage` | `backtestbench.explore.sessions.v1` | Open explore tabs |
| `localStorage` | `backtestbench.bot.sessions.v1` | Open bot tabs |
| `localStorage` | `backtestbench.workflow.market.v1` | Last workflow data source + instrument |
| `localStorage` | `backtestbench.*.dismissed.v1` | Closed tab ids |
| `data/explore-jobs/` | `{job_id}.json` | Server-side explore results |
| `data/bot-jobs/` | `{job_id}.json` | Server-side bot validation state |

Fingerprints (`lib/session-fingerprint.ts`):

- **Explore:** strategy + params + instrument + broker + date range
- **Bot:** strategy + params + instrument + broker + timeframe + rolling days

## Styling

All styles in `app/globals.css` — CSS variables, tabular numerals, Recharts charts. No CSS
modules.

## npm scripts

```bash
npm run dev      # development server (port 3000)
npm run build    # production build
npm run start    # serve production build
npm run lint     # ESLint
```

## Known limitations

- Backtest overrides live in `config/dashboard.json` → `strategy_overrides`.
- Trading bot does not place real broker orders.
- Explore stability is per-window analysis, not full walk-forward ranking.
- Each bootstrap/explore/bot run uses a separate Python subprocess.
- Only the latest dashboard state is kept; no run-history browser.
- UI copy is English; RUB values use `ru-RU` locale formatting.

## Verification

```bash
pytest tests -q
npm --prefix frontend ci
npm --prefix frontend run build
```

## Related docs

- [`../src/data_loader/README.md`](../src/data_loader/README.md) — candle load pipeline
- [`../docs/api_description.md`](../docs/api_description.md) — route contracts
- [`../docs/strategy_composable_engine_design.md`](../docs/strategy_composable_engine_design.md) — YAML strategies
