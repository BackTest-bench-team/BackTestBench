# Data Loader

Loads candle history from broker adapters into SQLite and serves it to the backtest engine,
optimizer, explore dock, and trading bot.

## End-to-end pipeline

```text
Broker adapter (T-Bank / Twelve Data / Bybit)
        │  get_candles()
        ▼
normalize_candle() + validate_candles()
        │  UTC timestamps, float OHLCV, OHLC sanity, dedupe
        ▼
DataLoader.store_candles()  →  SQLite (candles table)
        │
        ├─ load_engine_candles()  →  ExecutionEngine / charts (full OHLCV)
        └─ load_price_series()    →  composable strategies (timestamp + close)
                │
                ▼
        create_strategy() + ExecutionEngine.run()
                │
                ▼
        MetricsReport / ValidationMetricsReport / dashboard JSON
```

**Single-fetch contract:** `main.load_market_data()` and `ensure_candles_loaded()` fetch at
most once per process run (unless `force_fetch=True`). The optimizer, explore jobs, and
multi-strategy bootstrap all reuse the same `LoadedMarketData.candles` list.

## Validation (`validate_candles`)

Checked before storage:

| Rule | Detail |
|------|--------|
| Non-empty input | Raises `ValidationError` on `[]` |
| Required OHLC | `None` open/high/low/close rows are dropped |
| Volume | Negative volume dropped; missing volume → `0` |
| OHLC consistency | `high >= low`, wick brackets open/close |
| Duplicates | Same timestamp: last row wins |

**Not checked** (explicitly post-course / out of scope for #120):

- Missing bars / gap detection across the series
- Incremental sync or delta updates from broker
- Train vs validation dataset splits
- Corporate actions, splits, or session calendars

## Core API

```python
loader = DataLoader(use_cache=True)

# Store after broker fetch
loader.store_candles("SBER", "1h", raw_candles)

# Full candles for ExecutionEngine
candles = loader.load_engine_candles("SBER", "1h", start, end)

# Composable price series (timestamp + close)
bars = loader.load_price_series("SBER", "1h", start, end)

# Last N bars only — useful for trading bot / rolling windows
bars = loader.load_price_series("SBER", "1h", start, end, last_n_bars=168)

# One-shot load with broker fallback
market = await loader.ensure_candles_loaded(
    "SBER", "1h", start, end, fetch_from_broker,
    force_fetch=False,
)
# market.candles, market.price_series, market.source

loader.close()
```

`CandleCache` keeps the latest `(instrument, timeframe)` query in memory until
`store_candles()` clears it.

## Dashboard integration

`main.bootstrap_all()`:

1. `load_market_data()` → `ensure_candles_loaded()`
2. Reuses `market_data.candles` for every strategy backtest
3. Optimizer iterations never call the broker again in the same run

Trading bot (`src/engine/trading_bot.py`) uses the same loader with `force_fetch=True` on
each validation tick to refresh the recent window.

**Parallel bot jobs:** each `bot-job` subprocess owns its own `BrokerAdapter` and `DataLoader`
session. SQLite uses WAL locally; **Docker Compose uses `DELETE` journal mode** because WAL
sidecar files often break on bind-mounted volumes. `ensure_candles_loaded()` releases the read
transaction before awaiting the broker so multiple bots can write candles concurrently.

## Composable strategies

Composable YAML strategies precompute indicators from closing prices. After candles are in
SQLite, `load_price_series()` is the preferred export. Use `price_bars_to_candles()` only when
a caller needs minimal `Candle` rows from `(timestamp, price)` pairs.

## Deferred (issue #120 — not in current sprint)

- Incremental candle sync (append-only broker polling)
- Dedicated validation/holdout dataset storage
- Full gap/outlier analytics on stored series
