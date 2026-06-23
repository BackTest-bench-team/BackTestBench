# BackTestBench Frontend

The frontend is a Next.js 16 App Router dashboard for the current MVP. It displays the latest
backtest state and can launch the predefined Python pipeline.

Audited against `main` on June 23, 2026.

## Routes

### Page

- `/` — MVP dashboard with run metadata, pipeline stages, metrics, trade count, final
  portfolio values, and portfolio chart.

### Route handlers

- `POST /api/run`
  - requires `TINKOFF_TOKEN` from the repository `.env` file or process environment;
  - writes an initial `running` state to `data/runtime-dashboard.json`;
  - launches `python3 main.py` with a generated `RUN_ID`;
  - returns `202` with the run ID, or `500` on startup failure.
- `GET /api/dashboard`
  - reads `../data/runtime-dashboard.json`;
  - merges missing values with an idle default state;
  - returns `200` even when the runtime file is unavailable.

The route handlers are the implemented API for the dashboard. The FastAPI contract under
`docs/api_description.md` is planned and `src/api` is currently empty.

## Local Development

From the repository root:

```bash
cp .env.example .env
# set TINKOFF_TOKEN in .env
npm --prefix frontend ci
npm --prefix frontend run dev
```

Open <http://localhost:3000>.

The frontend locates the repository root by searching for `main.py` or `.env`. Keep the
standard monorepo layout when running it.

## Scripts

```bash
npm run dev
npm run lint
npm run build
npm run start
```

`next start` is not the container entry point. `Dockerfile.fullstack` uses `npm run dev`
because the current image is intended for the course MVP and PR smoke checks.

## Data Contract

The dashboard state includes:

- run ID, strategy/version, instrument, timeframe, and data source;
- `idle`, `running`, `completed`, or `error` status;
- current stage and per-stage statuses;
- total P&L, Sharpe ratio, max drawdown, win rate, and deposit baseline;
- equity points, trade count, and final portfolio values;
- message, error, and last-update timestamp.

The JSON file contains only the latest run. There is no durable run history.

## Known Limitations

- The run request has no input body; SBER, timeframe, date window, capital, and strategy
  parameters are currently set in `main.py`.
- The chart uses sequence indexes rather than market timestamps.
- Buy/sell markers are not displayed.
- Narrow viewports have horizontal overflow in parts of the dashboard.
- `npm run lint` currently fails at `app/page.tsx:227` because the initial
  `loadDashboard()` call synchronously triggers state updates from an effect
  (`react-hooks/set-state-in-effect`).
- The production build reports workspace-root and dynamic filesystem tracing warnings because
  the monorepo contains multiple lockfiles and route handlers perform filesystem access.

## Verification

```bash
npm ci
npm run lint
npm run build
```

Current status: build passes; lint exposes the known effect issue above.
