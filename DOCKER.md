# Docker Guide

This guide matches `docker-compose.yml`, `Dockerfile`, and `Dockerfile.fullstack` as of
July 7, 2026.

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

Open <http://localhost:3000>.

The repository is mounted at `/app`, and a named volume preserves
`/app/frontend/node_modules`. The dashboard calls Next.js API routes that spawn
`/app/main.py` subcommands (`bootstrap`, `stop`, `refresh-ranking`, `add-strategy`,
`delete-strategy`), which update `/app/data/runtime-dashboard.json` and may write
`/app/data/backtest.db` (SQLite candle cache).

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
- starts Next.js on `0.0.0.0:3000`.

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

As of July 7, 2026, the backend test suite contains **108 tests** (all passing) with
**78%** coverage of `src/`.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` using a self-hosted runner with
four jobs:

| Job | When | Checks |
|---|---|---|
| `backend-tests` | PR opened/synchronized | `pytest tests -q` |
| `frontend-checks` | PR opened/synchronized | `npm ci`, `npm run build`, `npm run lint` (lint non-blocking) |
| `docker-smoke` | PR opened/synchronized | `docker compose up -d --build`, 10 s uptime, `curl` HTTP 200 on port 8080 |
| `cleanup` | PR closed | `docker compose down --remove-orphans` |

The Docker job passes `TINKOFF_TOKEN` from GitHub Secrets and sets `APP_PORT=8080` to avoid
host port 80 conflicts on shared runners. Local Compose defaults to `${APP_PORT:-80}:3000`.

The full-stack image runs the Next.js **standalone** server (`node server.js`), not
`npm run start`.

## Troubleshooting

### `.env` not found

Create it with `cp .env.example .env`.

### Missing token

Set `TINKOFF_TOKEN` in `.env`. The pipeline cannot fetch T-Bank candles when the SQLite
cache is empty and no token is available.

### Port 80 or 3000 is busy

Set a different host port before starting Compose:

```bash
APP_PORT=8080 docker compose up -d --build
```

Or use a local `docker-compose.override.yml`:

```yaml
services:
  app:
    ports:
      - "3001:3000"
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

## Current Limitations

- The full-stack image serves the Next.js standalone build on port 3000 inside the container.
- The application is a single-container MVP, not the multi-container API/database/scheduler
  deployment described in the Week 2 target architecture.
- The default Compose service depends on a real T-Bank token when candles are not already
  cached in SQLite.
- Runtime state is file-backed and mounted from the host repository; relational run history
  is not persisted.
