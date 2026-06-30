# Data Loader

Loads candle history from broker adapters into the database and serves it to the simulation engine.

## Pipeline

1. **Normalize** — `normalize_candle()` converts adapter output to a single engine format (`YYYY-MM-DDTHH:MM:SS` UTC, float OHLCV).
2. **Validate** — `prepare_candles()` drops invalid rows, fills missing volume with `0`, and removes duplicate timestamps (last row wins).
3. **Store** — `DataLoader.store_candles()` upserts cleaned candles into the DB.
4. **Cache** — `CandleCache` keeps recently loaded `(instrument, timeframe)` series in memory; `load_candles()` checks the cache before querying the DB.

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
