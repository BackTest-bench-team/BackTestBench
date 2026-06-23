# Docker Guide

This guide matches `docker-compose.yml`, `Dockerfile`, and `Dockerfile.fullstack` as of
June 23, 2026.

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
`/app/frontend/node_modules`. The frontend's `POST /api/run` route starts `/app/main.py`,
which updates `/app/data/runtime-dashboard.json`.

Stop the stack:

```bash
docker compose down
```

## Compose Services

| Service | Default/profile | Purpose |
|---|---|---|
| `app` | default | Integrated Next.js dashboard and Python pipeline launcher |
| `backtest-app` | `backend` | Runs `python main.py` directly |
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
- starts `python main.py`;
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
docker compose logs app
docker compose down
```

Run backend tests:

```bash
docker compose --profile test run --rm test
```

As of June 23, 2026, the backend test suite contains 30 tests.

## CI

`.github/workflows/ci.yml` runs on pull requests to `main` using a self-hosted runner. It:

1. checks out the PR;
2. stops previous Compose services;
3. builds and starts the default Compose stack;
4. waits 10 seconds and fails if a service exited.

The workflow passes `TINKOFF_TOKEN` from GitHub Secrets to the Compose command. Cleanup on
PR close removes containers/images by legacy names; this should be reviewed because Compose
currently uses the fixed container name `backtest-bench-app`.

## Troubleshooting

### `.env` not found

Create it with `cp .env.example .env`.

### Missing token

Set `TINKOFF_TOKEN` in `.env`. The pipeline cannot fetch T-Bank candles without it.

### Port 3000 is busy

Stop the conflicting process or change the host-side mapping in a local
`docker-compose.override.yml`:

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
docker compose logs app
```

## Current Limitations

- The full-stack image runs the Next.js development server, not a production server.
- The application is a single-container MVP, not the multi-container API/database/scheduler
  deployment described in the Week 2 target architecture.
- The default Compose service depends on a real T-Bank token.
- Runtime state is file-backed and mounted from the host repository.
