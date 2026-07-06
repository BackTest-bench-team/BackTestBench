# Data Loader

Loads candle history from broker adapters into the database and serves it to the simulation engine.

## Pipeline

1. **Normalize** — `normalize_candle()` converts adapter output to a single engine format (`YYYY-MM-DDTHH:MM:SS` UTC, float OHLCV).
2. **Validate** — `prepare_candles()` drops invalid rows, fills missing volume with `0`, and removes duplicate timestamps (last row wins).
3. **Store** — `DataLoader.store_candles()` upserts cleaned candles into the DB.
4. **Cache** — `CandleCache` keeps recently loaded `(instrument, timeframe)` series in memory; `load_candles()` checks the cache before querying the DB.

## Composable price series (#118)

The composable engine consumes `(timestamp, price)` bars, not full OHLCV. After candles are in SQLite:

```python
bars = loader.load_price_series("SBER", "1h", start, end)
# list[PriceBar] — timestamp + close only
```

`load_price_series()` reuses the same DB query and in-memory cache as `load_engine_candles()`.

## Single load for optimizer / multi-strategy runs (#119)

**Contract:** load market data once per process run; pass the resulting candle list (or price series) into every backtest and into `RandomSearchExecutionEngine`. The optimizer must not call the broker per parameter combo.

```python
loader = DataLoader(use_cache=True)
market = await loader.ensure_candles_loaded(
    instrument, timeframe, start, end, fetch_from_broker,
)
# market.candles — full OHLCV for charts and ExecutionEngine
# market.price_series — (timestamp, close) for composable precompute

for strategy in strategies:
    run_backtest(strategy, market.candles)  # no second broker fetch

loader.close()
```

`main.load_market_data()` wraps this for the dashboard orchestrator: `bootstrap_all()` creates one `DataLoader`, calls `ensure_candles_loaded()` once, then reuses `market_data.candles` for all strategies and grid-search iterations.

First `load_candles()` / `load_price_series()` populates `CandleCache`; subsequent reads for the same `(instrument, timeframe)` in the same process hit memory until `store_candles()` clears the cache.

## Reusing existing data

Call `DataLoader.has_sufficient_data(instrument, timeframe, start, end)` before hitting an external API. When it returns `True`, `load_engine_candles()` for the same range is enough and no broker request is needed.

```python
loader = DataLoader(use_cache=True)
if loader.has_sufficient_data("SBER", "1h", start, end):
    candles = loader.load_engine_candles("SBER", "1h", start, end)
else:
    raw = await adapter.get_candles(...)
    loader.store_candles("SBER", "1h", raw)  # normalize + validate inside
    candles = loader.load_engine_candles("SBER", "1h", start, end)
```
