# Docker Guide

This guide matches `docker-compose.yml` as of **July 19, 2026**.

## Prerequisites

Create `.env` from the example and set a valid T-Bank token:

```bash
cp .env.example .env
```

```dotenv
TINKOFF_TOKEN=your_token_here
```

Compose services use `env_file: .env`; the file must exist. Never commit it.

## Integrated Dashboard

The default `app` service combines Python 3.12, Node.js 20, and the Next.js development
server:

```bash
docker compose up --build
```

Open <http://localhost> (or the host port from `APP_PORT`, default 80).

The `app` service bind-mounts host `.env`, `data/`, and `config/` into the container so
API tokens saved from the dashboard UI persist across `docker compose down` / `up`. Tokens
are **not** cleared on restart — only the ephemeral container filesystem is recreated.

The dashboard calls Next.js API routes that spawn `/app/main.py` subcommands (`bootstrap`,
`live-run-*`, `stop`, `refresh-ranking`, …), which update `/app/data/runtime-dashboard.json`
and `/app/data/backtest.db` (SQLite candle cache).

## Storing API keys (`.env`)

Compose loads `./.env` via `env_file` and bind-mounts it into the container (`./.env:/app/.env`).
The dashboard **Save token** action also writes keys into this file on the host.

**Acceptable for a private research VM** if you:

- never commit `.env` (keep `.gitignore` intact);
- restrict host access (`chmod 600 .env`, limited SSH/users);
- treat keys like passwords (rotate if leaked);
- accept that keys are **plain text on disk**, not in a secrets manager.

**Not ideal for production or multi-tenant servers** — prefer Docker secrets, Vault, or
cloud secret stores; inject env vars at deploy time instead of a world-readable file.

Bybit/Binance public kline endpoints often work without tokens. T-Bank and Twelve Data keys
grant API access to your brokerage/data account — protect accordingly.

Stop the stack:

```bash
docker compose down
```

## Compose Services

| Service | Default/profile | Purpose |
|---|---|---|
| `app` | default | Integrated Next.js dashboard and Python pipeline launcher |
| `backtest-app` | `backend` | Runs `python main.py bootstrap` directly |
| `test` | `test` | Runs `pytest tests -v` |
| `dev` | `dev` | Interactive Python 3.12 shell |

Commands:

```bash
docker compose --profile backend up --build backtest-app
docker compose --profile test run --rm test
docker compose --profile dev run --rm dev
```

## Images

### `Dockerfile.fullstack`

- base: `python:3.12-slim`;
- installs Node.js 20;
- installs Python dependencies from `requirements.txt`;
- installs frontend dependencies with `npm ci`;
- starts Next.js on `0.0.0.0:80`.

### `Dockerfile`

- base: `python:3.12-slim`;
- installs backend dependencies;
- starts `python main.py bootstrap`;
- is reused by the backend, test, and dev services.

The package metadata supports Python 3.10+, while the container runtime is currently pinned
to Python 3.12.

## Verification

Validate Compose without starting containers:

```bash
docker compose config
```

Build and smoke-run the integrated service:

```bash
docker compose up -d --build
docker compose ps
curl -fsS "http://localhost:${APP_PORT:-80}/"
docker compose logs app
docker compose down
```

If port 80 is busy locally, set `APP_PORT=8080` before `docker compose up`.

Run backend tests:

```bash
docker compose --profile test run --rm test
```

As of July 19, 2026, run the suite via Compose or locally (`pytest tests -q`). Exact test
count and coverage vary by branch; CI runs the full suite on every PR.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` using GitHub-hosted
`ubuntu-latest` runners with three jobs:

| Job | When | Checks |
|---|---|---|
| `backend-tests` | PR opened/synchronized | Python 3.12, `pytest tests -q` |
| `frontend-checks` | PR opened/synchronized | Node 20, `npm ci`, `npm run build`, `npm run lint` (lint non-blocking) |
| `docker-smoke` | PR opened/synchronized | `docker compose up -d --build`, 10 s uptime, `curl` HTTP 200 on port 8080 |

The Docker job creates `.env` from the `TINKOFF_TOKEN` GitHub secret and sets
`APP_PORT=8080`. Ephemeral runners tear down after each job, so no separate cleanup job is
required on PR close. Local Compose defaults to `${APP_PORT:-80}:80`.

The full-stack image runs the Next.js **standalone** server (`node server.js`), not
`npm run start`.

## Troubleshooting

### `.env` not found

Create it with `cp .env.example .env`.

### Missing token

Set `TINKOFF_TOKEN` in `.env`. The pipeline cannot fetch T-Bank candles when the SQLite
cache is empty and no token is available.

### Port 80 is busy

Set a different host port before starting Compose:

```bash
APP_PORT=8080 docker compose up -d --build
```

Or use a local `docker-compose.override.yml`:

```yaml
services:
  app:
    ports:
      - "8080:80"
```

### Reinstall frontend dependencies

Remove the named volume and rebuild:

```bash
docker compose down -v
docker compose build --no-cache app
```

### Inspect the pipeline state

```bash
docker compose exec app cat /app/data/runtime-dashboard.json
docker compose exec app ls -la /app/data/backtest.db
docker compose logs app
```

### SQLite `disk I/O error` on startup

The candle cache uses SQLite at `data/backtest.db`. **WAL mode** (`-wal` / `-shm` sidecar files)
often fails on Docker **bind-mounted** host folders (especially on Windows), which surfaces as:

```text
(sqlite3.OperationalError) disk I/O error
```

**Fix (built-in):** the `app` service sets `SQLITE_JOURNAL_MODE=DELETE`, and the Python layer
auto-selects `DELETE` when `/.dockerenv` is present.

If the error persists after an unclean shutdown, remove stale sidecars on the host and restart:

```bash
docker compose down
rm -f data/backtest.db-wal data/backtest.db-shm data/backtest.db-journal
docker compose up --build
```

To wipe the cache entirely (candles will be re-fetched from the broker):

```bash
docker compose down
rm -f data/backtest.db data/backtest.db-*
docker compose up
```

Ensure the host `data/` directory exists and is writable:

```bash
mkdir -p data
```

## Current Limitations

- The full-stack image serves the Next.js standalone build on port 80 inside the container.
- The application is a single-container MVP, not the multi-container API/database/scheduler
  deployment described in the Week 2 target architecture.
- The default Compose service depends on a real T-Bank token when candles are not already
  cached in SQLite.
- Runtime state is file-backed and mounted from the host repository; relational run history
  is not persisted.
