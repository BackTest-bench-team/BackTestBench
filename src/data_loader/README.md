# Data Loader

Loads candle history into SQLite and serves it to the backtest engine and Live refresh.

## Pipeline

```text
Broker adapter (T-Bank / Twelve Data / Bybit / Binance)
        │  get_candles() — paginated inside adapter for large ranges
        ▼
backtest_fetch.ensure_backtest_candles()  — chunked sequential fetch, gap fill
        │  validate_candles() + upsert
        ▼
SQLite data/backtest.db (candles table)
        │
        └─ load_engine_candles() → ExecutionEngine / metrics / charts
```

**Bootstrap path:** `main.load_candles_for_backtest()` → `ensure_backtest_candles()`.

- Same instrument + timeframe: reuse DB; fetch only missing date ranges.
- Timeframe change on Run backtest: clears cached candles for the old TF.
- Lookback decrease: serve from DB only; increase: fetch additional chunks.

**Live refresh:** same loader on each tick (`live_run_tick_command`).

**Trading bot module** (`src/engine/trading_bot.py`) still uses `DataLoader.ensure_candles_loaded()` directly for optional rolling validation scripts — separate from the dashboard.

## Validation (`validate_candles`)

Non-empty input, valid OHLC, dedupe by timestamp before upsert.

## Core API

```python
from src.data_loader.backtest_fetch import ensure_backtest_candles

candles, source, api_calls = await ensure_backtest_candles(
    config, from_dt, to_dt, fetch_candles_from_api, on_progress=callback,
)
```

```python
loader = DataLoader(use_cache=False)
loader.store_candles("SBER", "1h", raw_candles)
candles = loader.load_engine_candles("SBER", "1h", start, end)
loader.close()
```

## Docker / SQLite

- Local dev: WAL journal mode when not in Docker.
- Compose `app` service: `SQLITE_JOURNAL_MODE=DELETE` (bind mounts).
- Cache file: `data/backtest.db` (gitignored).

## Deferred

- Dedicated holdout dataset tables
- Corporate actions / session calendars
