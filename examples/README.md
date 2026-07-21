# Examples — Broker Adapter Usage

This folder contains ready-to-run examples for the **broker adapter** layer. The
main entry point is [`tbank_adapter_usage.py`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/examples/tbank_adapter_usage.py), which
provides a thin, friendly wrapper around the low-level adapters
([`TBankAdapter`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/broker_adapter/tbank.py),
[`TwelveDataAdapter`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/broker_adapter/twelvedata.py),
[`BybitAdapter`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/broker_adapter/bybit.py), and
[`BinanceAdapter`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/broker_adapter/binance.py)) for fetching historical
market candles (OHLC/V) and running simple backtests.

> The file's primary purpose is **parsing/fetching data from a data API**.
> You pick which API to use, and all candle-fetching logic goes through the
> `run_fetch_candles` function (synchronous) or `fetch_candles` (async). All
> adapters return the **same unified `Candle` model**, so downstream code
> (strategies, the execution engine, backtests) is identical regardless of the
> source.

---

## Data sources

The example supports four data providers:

| `source`     | Provider                            | Markets                                 | Token env var      | Token required? |
|--------------|-------------------------------------|-----------------------------------------|--------------------|-----------------|
| `"tbank"`     | T-Bank (Tinkoff Investments) API v2 | Russian equities (MOEX TQBR: SBER, GAZP, LKOH, …) | `TINKOFF_TOKEN`    | Yes             |
| `"twelvedata"` | [twelvedata.com](https://twelvedata.com) REST API | Global equities, FX, crypto (AAPL, MSFT, ETH/BTC, …) | `TWELVEDATA_TOKEN` | Yes             |
| `"bybit"`     | [Bybit](https://bybit-exchange.github.io/docs/v5/market/kline) V5 kline API | Crypto spot pairs (BTCUSDT, ETHUSDT, …) | `BYBIT_TOKEN`      | **No** (endpoint is public) |
| `"binance"`   | [Binance](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints) Spot kline API (`/api/v3/klines`) | Crypto spot pairs & fiat-quoted stablecoin pairs (BTCUSDT, ETHBTC, EURUSDT, …) | `BINANCE_TOKEN`    | **No** (endpoint is public) |

The source is chosen either **per-call** via the `source=...` argument, or
**globally** via the `DATA_SOURCE` environment variable (defaults to `tbank`):

```dotenv
# .env — optional default. Can still be overridden per call with source=...
DATA_SOURCE=bybit
```

```python
# Per-call override wins regardless of DATA_SOURCE:
run_fetch_candles(instrument="AAPL", source="twelvedata", timeframe="1d", days=60)
run_fetch_candles(instrument="SBER", source="tbank", timeframe="1h", days=7)
run_fetch_candles(instrument="BTCUSDT", source="bybit", timeframe="1d", days=60)
run_fetch_candles(instrument="ETHBTC", source="binance", timeframe="1d", days=60)
```

The **timeframe format is shared** across all sources (`1m`, `5m`, `1h`, `1d`,
`1w`, `1M`) — each adapter maps these to its own internal interval names, so you
use identical parameters either way.

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Quick start](#quick-start)
3. [Public functions](#public-functions)
4. [`run_fetch_candles` / `fetch_candles` parameters](#run_fetch_candles--fetch_candles-parameters)
   - [Choosing a data source](#choosing-a-data-source)
   - [Instrument (tickers)](#instrument-tickers)
   - [Timeframe](#timeframe)
   - [History limits (`days`)](#history-limits-days)
   - [Date range](#date-range)
   - [Environment & token](#environment--token)
5. [Return format](#return-format)
6. [Validation rules](#validation-rules)
7. [`run_backtest` parameters](#run_backtest-parameters)
8. [Errors and exceptions](#errors-and-exceptions)
9. [Examples](#examples)
10. [Limitations](#limitations)

---

## Prerequisites

1. **An API token** for at least one provider:

   - **T-Bank** — generate a token in the T-Bank Invest app or via the
     [API console](https://www.tbank.ru/about/business/ita/invest-api/). A
     *read-only* token is sufficient and recommended for candle data.
   - **Twelve Data** — get a free API key at
     [twelvedata.com](https://twelvedata.com/pricing) (free tier covers the
     common case; higher tiers lift rate limits).
   - **Bybit** — *no token required* for historical candle data (the V5
     `market/kline` endpoint is public). You can still set `BYBIT_TOKEN`; it is
     accepted for parity but not sent with kline requests.
   - **Binance** — *no token required* for historical candle data (the Spot
     `/api/v3/klines` endpoint is public). You can still set `BINANCE_TOKEN`;
     it is accepted for parity but not sent with kline requests.

2. **A `.env` file** in the project root with the token(s) you want to use:

   ```dotenv
   # T-Bank (use source="tbank")
   TINKOFF_TOKEN=your_tbank_token_here

   # Twelve Data (use source="twelvedata")
   TWELVEDATA_TOKEN=your_twelvedata_key_here

   # Bybit (use source="bybit") — optional, the kline endpoint is public
   # BYBIT_TOKEN=your_bybit_key_here

   # Binance (use source="binance") — optional, the kline endpoint is public
   # BINANCE_TOKEN=your_binance_key_here

   # Optional default source. Omit to default to "tbank".
   # DATA_SOURCE=tbank
   ```

   The module loads `.env` automatically on import (`dotenv`), so normally you
   do not pass the token explicitly.

3. **Dependencies installed** (`aiohttp`, `python-dotenv`, protobuf, etc.) — see
   the project [`requirements.txt`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/requirements.txt).

---

## Quick start

```python
from examples.tbank_adapter_usage import run_fetch_candles

# Default source (DATA_SOURCE / "tbank") — last 7 days of 1h candles for SBER
candles = run_fetch_candles(instrument="SBER", timeframe="1h", days=7)

# Twelve Data explicitly — last 60 days of daily candles for AAPL
candles = run_fetch_candles(
    instrument="AAPL",
    source="twelvedata",
    timeframe="1d",
    days=60,
)

# Bybit explicitly — last 60 days of daily candles for BTCUSDT (no token needed)
candles = run_fetch_candles(
    instrument="BTCUSDT",
    source="bybit",
    timeframe="1d",
    days=60,
)

# Binance explicitly — last 60 days of daily candles for ETHBTC (no token needed)
candles = run_fetch_candles(
    instrument="ETHBTC",
    source="binance",
    timeframe="1d",
    days=60,
)

print(f"Fetched {len(candles)} candles")
for c in candles[:3]:
    print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}")
```

Running the file directly executes built-in demos for all four providers:

```bash
python examples/tbank_adapter_usage.py
```

Each demo skips gracefully (with a clear message) if its token isn't set (or, for
Bybit/Binance, if the request fails), so the file runs cleanly with any subset of
tokens.

---

## Public functions

| Function            | Type   | Description                                                            |
|---------------------|--------|------------------------------------------------------------------------|
| `run_fetch_candles` | sync   | Fetch historical candles. **Main entry point for data parsing.**       |
| `fetch_candles`     | async  | Underlying coroutine awaited by `run_fetch_candles`.                   |
| `run_backtest`      | sync   | Fetch candles and run the MA-Crossover backtest on them.               |
| `get_token`         | sync   | Helper that reads the right token (`TINKOFF_TOKEN` / `TWELVEDATA_TOKEN` / `BYBIT_TOKEN` / `BINANCE_TOKEN`) for the given source. |

---

## `run_fetch_candles` / `fetch_candles` parameters

Both functions share the same signature:

```python
run_fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    source: Optional[str] = None,     # "tbank" | "twelvedata"; default: DATA_SOURCE / "tbank"
    from_date: Optional[str] = None,  # "YYYY-MM-DD"
    to_date: Optional[str] = None,    # "YYYY-MM-DD"
    use_sandbox: bool = False,        # T-Bank only
    token: Optional[str] = None,
) -> List[Candle]
```

| Parameter     | Type             | Default            | Description                                                                                       |
|---------------|------------------|--------------------|---------------------------------------------------------------------------------------------------|
| `instrument`  | `str`            | `"SBER"`           | Ticker. T-Bank: `SBER`, `GAZP`, `LKOH` or a FIGI. Twelve Data: `AAPL`, `MSFT`, `ETH/BTC`. Bybit / Binance: `BTCUSDT`, `ETHUSDT`, `ETHBTC`, `EURUSDT`. See [tickers](#instrument-tickers). |
| `timeframe`   | `str`            | `"1h"`             | Candle granularity, **same format for all sources**. Minimum resolution is `1m`. See [timeframes](#timeframe). |
| `days`        | `int`            | `7`                | History depth in days, counting back from `to_date`/now. Ignored if `from_date` is given. Caps differ per source — see [history limits](#history-limits-days). |
| `source`      | `Optional[str]`  | `DATA_SOURCE`/`"tbank"` | Data API: `"tbank"`, `"twelvedata"`, `"bybit"`, or `"binance"`. See [choosing a data source](#choosing-a-data-source). |
| `from_date`   | `Optional[str]`  | `None`             | Start date `YYYY-MM-DD`. Overrides `days`.                                                         |
| `to_date`     | `Optional[str]`  | `None`             | End date `YYYY-MM-DD`. Defaults to *now*.                                                          |
| `use_sandbox` | `bool`           | `False`            | T-Bank **sandbox** host (ignored by Twelve Data).                                                  |
| `token`       | `Optional[str]`  | `None`             | API token. If omitted, loaded from the matching env var via `get_token()`.                        |

> **`from_date` overrides `days`.** If you pass both, `days` is ignored.
> If you pass neither `from_date` nor `to_date`, the window is `[now - days, now]`.

### Choosing a data source

The `source` parameter selects the adapter. It is resolved as follows:

1. If `source=` is given, it's used (case-insensitive).
2. Otherwise the `DATA_SOURCE` env var is read.
3. Otherwise it defaults to `"tbank"`.

Anything other than `"tbank"` / `"twelvedata"` / `"bybit"` / `"binance"` raises
`ValueError`. The chosen source determines which token env var is read
(`TINKOFF_TOKEN`, `TWELVEDATA_TOKEN`, `BYBIT_TOKEN`, or `BINANCE_TOKEN`) and
which history-depth caps apply.

```python
# Explicit per call
fetch_candles(source="twelvedata", instrument="AAPL", timeframe="1d", days=30)

# Implicit, via .env:  DATA_SOURCE=twelvedata
fetch_candles(instrument="AAPL", timeframe="1d", days=30)
```

### Instrument (tickers)

The `instrument` value you pass depends on the chosen `source`. All adapters
return the same `Candle` model regardless of the underlying symbol.

#### T-Bank (`source="tbank"`)

Accepts any ticker listed in the **TQBR** trading mode of MOEX (Moscow
Exchange), passed by its standard short symbol:

| Ticker  | Issuer                    | Ticker  | Issuer                    |
|---------|---------------------------|---------|---------------------------|
| `SBER`  | Сбербанк                  | `GMKN`  | Норникель                 |
| `GAZP`  | Газпром                   | `YDEX`  | Яндекс                    |
| `LKOH`  | Лукойл                    | `OZON`  | Ozon                      |
| `ROSN`  | Роснефть                  | `MGNT`  | Магнит                    |
| `NVTK`  | Новатэк                   | `MTSS`  | МТС                       |
| `TATN`  | Татнефть                  | `CHMF`  | Северсталь                |
| `VTBR`  | ВТБ                       | `NLMK`  | НЛМК                      |
| `PLZL`  | Полюс                     | `MOEX`  | Московская биржа          |
| `AFKS`  | Sistema                   | `RUAL`  | РУСАЛ                     |

The list above is illustrative, not exhaustive — any TQBR ticker the T-Bank API
knows about will work. The adapter resolves the ticker to a FIGI automatically.

**FIGI (T-Bank only).** A FIGI may also be passed directly instead of a ticker:
any value starting with `BBG` or exactly 12 characters long is treated as a
FIGI and looked up as-is. Example: `BBG000S8XPJ4` (SBER ADR). FIGIs are unique
per instrument, so they are never ambiguous.

A symbol the T-Bank API cannot resolve raises `InvalidInstrumentError`.

#### Twelve Data (`source="twelvedata"`)

Twelve Data covers **global equities, ETFs, forex, crypto, and (on paid plans)
indices**. The symbol format depends on the asset class:

| Asset class       | `instrument` format          | Examples                          | Notes                                                  |
|-------------------|------------------------------|-----------------------------------|--------------------------------------------------------|
| Stocks            | `SYMBOL`                     | `AAPL`, `MSFT`, `TSLA`, `SAP`     | Bare ticker, no exchange suffix.                       |
| ETFs              | `SYMBOL`                     | `SPY`, `QQQ`, `AAAA`              | Same format as stocks.                                 |
| Forex             | `BASE/QUOTE`                 | `EUR/USD`, `GBP/USD`, `USD/JPY`   | ISO currency codes, slash-separated.                   |
| Crypto            | `BASE/QUOTE`                 | `BTC/USD`, `ETH/BTC`, `USDT/USD`  | Same `BASE/QUOTE` shape as forex.                      |
| Indices (paid)    | `SYMBOL`                     | `SPX`, `NDX`                      | Only on Grow/Venture plans; 404 on free tier.          |

> **Slash matters.** Forex/crypto pairs must use the `BASE/QUOTE` form —
> `EUR/USD` works, `EURUSD` does **not**.

**Ambiguity across exchanges.** The same ticker often trades on multiple
exchanges (e.g. `AAPL` is listed on NASDAQ, plus CEDEARs/DRs in Argentina,
Canada, Mexico, …; `SHOP` trades on both NASDAQ and TSX). This example does not
expose Twelve Data's `exchange=`/`mic_code=` disambiguation parameters, so a
bare ticker resolves to Twelve Data's **primary listing** (verified: bare
`AAPL` → NASDAQ `XNGS`). If you need a specific listing, open an issue — it is
a small adapter extension to forward `exchange=`/`mic_code=`.

**Index support is limited on the free tier.** Plain index tickers like
`GSPC`/`IXIC`/`DJI` return `404`; major ones (`SPX`, `NDX`) require a paid
plan. Use an ETF proxy on free tiers instead (e.g. `SPY` for S&P 500, `QQQ`
for Nasdaq-100).

A symbol Twelve Data cannot resolve returns `404` and is raised as
`InvalidInstrumentError`; exceeding your plan returns a `BrokerError` (429 for
rate/credit limits).

**Finding a valid symbol.** Use Twelve Data's reference endpoints to confirm a
symbol before fetching candles:

```python
import asyncio, aiohttp, os

async def search(symbol):
    async with aiohttp.ClientSession() as s:
        async with s.get(
            "https://api.twelvedata.com/symbol_search",
            params={"symbol": symbol, "apikey": os.environ["TWELVEDATA_TOKEN"]},
        ) as r:
            return await r.json()

print(asyncio.run(search("AAPL")))
# -> [{'symbol':'AAPL','instrument_name':'Apple Inc.','exchange':'NASDAQ',
#      'mic_code':'XNGS','instrument_type':'Common Stock','country':'United States'}, ...]
```

The full symbol lists are also browsable at the
[Twelve Data request builder](https://twelvedata.com/request-builder) and in
the [API docs](https://twelvedata.com/docs#reference-data).

#### Bybit (`source="bybit"`)

Bybit is a crypto exchange. Symbols are **base+quote concatenated without a
separator** (unlike Twelve Data's `BASE/QUOTE`):

| Asset class | `instrument` format  | Examples                              | Notes                                            |
|-------------|----------------------|---------------------------------------|--------------------------------------------------|
| Spot pairs  | `BASEQUOTE`          | `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT` | Default category. Quote is typically `USDT`/`USDC`. |
| Perpetuals  | `BASEQUOTE`          | `BTCUSDT`, `ETHUSDT`                  | Linear (USDT-margined). Set via `BybitAdapter(category="linear")`. |
| Inverse     | `BASEUSD`            | `BTCUSD`, `ETHUSD`                    | Inverse contracts. Set via `BybitAdapter(category="inverse")`. |

**Default category is `spot`.** This example wires `BybitAdapter(category="spot")`
in `_build_adapter`, so `BTCUSDT` resolves to the **spot** pair. Spot and
perpetual prices/volumes differ for the same symbol — to fetch perpetuals,
construct the adapter directly:

```python
import asyncio
from src.broker_adapter import BybitAdapter

async def main():
    async with BybitAdapter(category="linear") as adapter:
        return await adapter.get_candles(
            instrument="BTCUSDT",
            timeframe="1h",
            from_dt=__import__("datetime").datetime(2024, 1, 1),
            to_dt=__import__("datetime").datetime(2024, 2, 1),
        )

candles = asyncio.run(main())
```

Common spot pairs (illustrative — Bybit lists hundreds):

| Symbol      | Pair              | Symbol      | Pair              |
|-------------|-------------------|-------------|-------------------|
| `BTCUSDT`   | Bitcoin / Tether  | `SOLUSDT`   | Solana / Tether   |
| `ETHUSDT`   | Ethereum / Tether | `XRPUSDT`   | XRP / Tether      |
| `BTCUSDC`   | Bitcoin / USD Coin| `DOGEUSDT`  | Dogecoin / Tether |
| `ETHUSDC`   | Ethereum / USD Coin| `ADAUSDT`  | Cardano / Tether  |
| `BNBUSDT`   | BNB / Tether      | `AVAXUSDT`  | Avalanche / Tether|

More information in file List_of_spots_bybit.txt
A symbol Bybit doesn't recognise returns `retCode 10001` and is raised as
`InvalidInstrumentError`. **No token is required** — the kline endpoint is
public. The full instrument list is available via the
[`instruments-info`](https://bybit-exchange.github.io/docs/v5/market/instrument)
endpoint or the Bybit UI.

#### Binance (`source="binance"`)

Binance is a crypto exchange. Like Bybit, symbols are **base+quote concatenated
without a separator** (no slash). The adapter targets the **spot** market only
(`/api/v3/klines`); Binance Futures, Options, and other derivatives are not
exposed.

| Asset class                  | `instrument` format  | Examples                              | Notes                                            |
|------------------------------|----------------------|---------------------------------------|--------------------------------------------------|
| Spot crypto pairs            | `BASEQUOTE`          | `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `XRPUSDT`, `DOGEUSDT` | Default (and only) category. Quote is typically `USDT`/`USDC`/`BTC`/`ETH`/`BNB`. |
| Crypto-to-crypto             | `BASEQUOTE`          | `ETHBTC`, `LTCBTC`, `ADABNB`          | Same `BASEQUOTE` shape; useful for relative-value views. |
| Fiat-quoted stablecoin pairs | `BASEQUOTE`          | `EURUSDT`, `GBPUSDT`, `JPYUSDT`, `BRLUSDT` | Binance lists a number of fiat-quoted stablecoin pairs that behave like FX. |

**Spot only.** This example wires `BinanceAdapter(token=token)` in
`_build_adapter`, so all symbols resolve to spot. Binance Spot does not have a
`category=` parameter — for futures/derivatives you would need a separate
adapter (Binance Futures, `/fapi/v1/klines`), which is not implemented here.

```python
import asyncio
from datetime import datetime
from src.broker_adapter import BinanceAdapter

async def main():
    async with BinanceAdapter(token=None) as adapter:
        return await adapter.get_candles(
            instrument="BTCUSDT",
            timeframe="1h",
            from_dt=datetime(2024, 1, 1),
            to_dt=datetime(2024, 2, 1),
        )

candles = asyncio.run(main())
```

Common spot pairs (illustrative — Binance lists thousands):

| Symbol      | Pair              | Symbol      | Pair              |
|-------------|-------------------|-------------|-------------------|
| `BTCUSDT`   | Bitcoin / Tether  | `SOLUSDT`   | Solana / Tether   |
| `ETHUSDT`   | Ethereum / Tether | `XRPUSDT`   | XRP / Tether      |
| `BTCUSDC`   | Bitcoin / USD Coin| `DOGEUSDT`  | Dogecoin / Tether |
| `ETHBTC`    | Ethereum / Bitcoin| `ADAUSDT`   | Cardano / Tether  |
| `BNBUSDT`   | BNB / Tether      | `EURUSDT`   | Euro / Tether     |

A symbol Binance doesn't recognise returns HTTP `400` with a body like
`{"code": -1121, "msg": "Invalid symbol."}` and is raised as
`InvalidInstrumentError`. **No token is required** — the kline endpoint is
public. The full instrument list is available via the
[`exchangeInfo`](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
endpoint or the Binance UI.

### Timeframe

The same set of timeframe values works for **all four** sources:

| Value  | Meaning   | Max `days` — T-Bank sandbox | Max `days` — Twelve Data | Max `days` — Bybit | Max `days` — Binance |
|--------|-----------|-----------------------------|--------------------------|--------------------|----------------------|
| `1m`   | 1 minute  | 1                           | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `5m`   | 5 minutes | 7                           | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `15m`  | 15 minutes| 24                          | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `30m`  | 30 minutes| 25                          | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `1h`   | 1 hour    | 100                         | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `1d`   | 1 day     | 2400                        | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `1w`   | 1 week    | 2100                        | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |
| `1M`   | 1 month   | 3600                        | 3650 (soft cap)          | 3650 (soft cap)    | 3650 (soft cap)      |

- **Minimum timeframe is `1m`.** Sub-minute intervals (`1s`, `30s`, `15s`, …)
  are **rejected** with a `ValueError` before any network call — no provider
  serves finer granularity.
- The supported set is exported as `TIMEFRAMES`; the minimum is exported as
  `MIN_TIMEFRAME = "1m"`.
- Unknown values (e.g. `"2m"`, `"hour"`) are also rejected.
- Surrounding whitespace is tolerated and stripped.

Internally, each adapter maps these onto its interval names (Twelve Data:
`1min`/`5min`/`1h`/`1day`/`1week`/`1month`; Bybit: `1`/`5`/`15`/`30`/`60`/`D`/`W`/`M`;
Binance uses the same labels as this module — `1m`/`5m`/`15m`/`30m`/`1h`/`1d`/`1w`/`1M`,
so the mapping is identity); you never need to use those names yourself.

### History limits (`days`)

**T-Bank (`source="tbank"`).** The sandbox's `GetCandles` endpoint caps how
wide a date range it will serve. For **intraday** timeframes, a range that is
too wide fails with gRPC error `30014` and returns **no candles at all**. So
`days` is validated up front against a per-timeframe cap, and an oversized
request raises a `ValueError` instead of an empty response. The caps are
exported as `DAYS_LIMIT_BY_TIMEFRAME`:

```python
DAYS_LIMIT_BY_TIMEFRAME = {
    "1m": 1,    "5m": 7,    "15m": 24,   "30m": 25,
    "1h": 100,  "1d": 2400,  "1w": 2100,   "1M": 3600,
}
```

These intraday limits were measured empirically (exponential-then-binary search
probing the sandbox for the largest `days` that still returns a non-empty candle
list for `SBER`). Re-run such a probe if the sandbox changes.

**Twelve Data (`source="twelvedata"`).** There is no per-timeframe sandbox cap;
only a generous sanity ceiling (`_MAX_DAYS_TWELVEDATA = 3650`) guards against
pathological requests. Use `from_date`/`to_date` for very long histories.

**Bybit (`source="bybit"`).** No per-timeframe cap. Bybit caps each request at
**200 candles**, but the adapter **paginates transparently** — wide windows
(e.g. a year of 1-minute bars) are split into 200-candle pages internally, so a
single `fetch_candles` call returns the whole range. Only the soft ceiling
(`_MAX_DAYS_BYBIT = 3650`) applies.

**Binance (`source="binance"`).** No per-timeframe cap. Binance caps each kline
request at **1000 candles**, but the adapter **paginates transparently** — wide
windows are split into 1000-candle pages internally (forward from `startTime`,
skipping past the last received open time to avoid duplicates), so a single
`fetch_candles` call returns the whole range. Only the soft ceiling
(`_MAX_DAYS_BINANCE = 3650`) applies.

> **Note:** `days` is only validated when `from_date` is *not* supplied (i.e.
> when the window is derived from `days`). If you pass explicit `from_date` /
> `to_date`, the window is sent to the API as-is, and an overly wide T-Bank
> intraday range will come back empty.

### Date range

- Format: `"YYYY-MM-DD"` (parsed strictly via `datetime.strptime`).
- If `to_date` is omitted it defaults to the current moment (`datetime.now()`).
- If `from_date` is omitted it is computed as `to_date - days`; in that case
  `days` is validated against the [history limits](#history-limits-days).
- If `from_date` is supplied explicitly, it overrides `days` and the window is
  not pre-validated for width — an overly wide T-Bank intraday range returns an
  empty list from the API (no exception).

### Environment & token

- `source="tbank"`:
  - `use_sandbox=False` (default) → `https://invest-public-api.tbank.ru`.
  - `use_sandbox=True`  → `https://sandbox-invest-public-api.tbank.ru`.
  - `token=None` (default) → loaded from `TINKOFF_TOKEN` via `get_token("tbank")`.
- `source="twelvedata"`:
  - `https://api.twelvedata.com` is always used (no sandbox).
  - `token=None` (default) → loaded from `TWELVEDATA_TOKEN` via
    `get_token("twelvedata")`.
- `source="bybit"`:
  - `https://api.bybit.com` is always used (no sandbox).
  - `token=None` (default) → `BYBIT_TOKEN` is **optional**; if unset,
    `get_token("bybit")` returns `None` (the kline endpoint is public).
  - The token is **not** sent with kline requests.
- `source="binance"`:
  - `https://api.binance.com` is always used (no sandbox).
  - `token=None` (default) → `BINANCE_TOKEN` is **optional**; if unset,
    `get_token("binance")` returns `None` (the kline endpoint is public).
  - The token is **not** sent with kline requests.
- `DATA_SOURCE` (env) sets the default source when `source=` isn't passed;
  defaults to `"tbank"` if unset.

---

## Return format

Both `fetch_candles` and `run_fetch_candles` return a `List[Candle]` in
**chronological order** (oldest first). `Candle` is the unified dataclass from
[`src/engine/models.py`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/engine/models.py):

```python
@dataclass
class Candle:
    timestamp: str   # ISO-8601 without tz: "YYYY-MM-DDTHH:MM:SS"
    open:     float  # OHLC are prices in the instrument's currency
    high:     float
    low:      float
    close:     float
    volume:    float  # traded volume for the candle's interval
```

- **`timestamp`** is a string in `"YYYY-MM-DDTHH:MM:SS"` format. T-Bank returns
  UTC; Twelve Data returns the exchange's timezone; **Bybit and Binance return
  UTC**. For daily/weekly/monthly intervals the time component is `00:00:00`.
- **`open/high/low/close`** are floats. T-Bank values come from the API's
  `Quotation` (units + nano) with full precision; Twelve Data, Bybit, and
  Binance values come as decimal strings.
- **`volume`** is a float. If Twelve Data omits it (e.g. for some FX pairs), it
  defaults to `0.0`. Bybit and Binance always provide volume (in base units).
- The list is returned oldest-first. You can iterate it directly, or hand it to
  any component that expects `List[Candle]` — e.g. `ExecutionEngine.run(...)`.

---

## Validation rules

The module validates user **inputs** before any network call. The following
raise `ValueError` with a descriptive message:

1. **Source** (`_resolve_source`)
   - Must be one of `("tbank", "twelvedata", "bybit", "binance")`. Anything else is rejected.
2. **Timeframe** (`_validate_timeframe`)
   - Must be one of `TIMEFRAMES`.
   - Sub-minute intervals (`*s`) are explicitly rejected — minimum is `1m`.
3. **History depth** (`_validate_days`), checked only when the window is derived
   from `days` (i.e. `from_date` not supplied):
   - `days` must be a positive integer.
   - For `source="tbank"`: must not exceed the per-timeframe cap in
     `DAYS_LIMIT_BY_TIMEFRAME`.
   - For `source="twelvedata"`/`"bybit"`/`"binance"`: must not exceed the soft cap (3650).

No validation is performed on the candles themselves — the adapter returns
whatever the API delivers. An empty result set (no candles in range) is returned
as an empty list; that is *not* an error.

---

## `run_backtest` parameters

`run_backtest` extends the fetch parameters with backtest-specific ones:

```python
run_backtest(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 30,
    initial_capital: float = 100000.0,
    strategy_params: Optional[Dict[str, Any]] = None,  # default: fast=10, slow=30, order_size=1.0
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]
```

Returns a dict with keys:

| Key               | Type                | Description                                            |
|-------------------|---------------------|--------------------------------------------------------|
| `trade_log`       | `list[Trade]`       | List of executed trades (may be empty).                |
| `final_portfolio` | `Portfolio` or `None` | Portfolio state after the last candle.               |
| `candles_count`   | `int`               | Number of candles that were fetched and fed in.        |

If no candles are fetched, it returns `{"trade_log": [], "final_portfolio": None, "candles_count": 0}`.

`strategy_params` defaults to `{"fast": 10, "slow": 30, "order_size": 1.0}` for
the `MACrossover` strategy. The same timeframe/instrument/source validation
rules apply as for fetching.

---

## Errors and exceptions

| Exception                     | When it is raised                                                                 |
|-------------------------------|-----------------------------------------------------------------------------------|
| `ValueError`                  | Unsupported `source`, unsupported/`sub-1m` `timeframe`, or `days` larger than the source's cap. |
| `ValueError` (from `get_token`)| The token env var for a source that *requires* it (`tbank`/`twelvedata`) is not set and no `token=` was passed. Not raised for `bybit`/`binance` (token optional).  |
| `AuthenticationError`         | The token is invalid/expired (T-Bank gRPC status 16; Twelve Data HTTP 401/403). Not raised by Bybit/Binance kline (public).  |
| `InvalidInstrumentError`      | The ticker/symbol cannot be resolved by the API (T-Bank lookup, Twelve Data 400/404, Bybit `retCode 10001`, Binance HTTP 400 `code -1121`).  |
| `RateLimitError`              | A rate limit is hit (T-Bank gRPC status 8; Twelve Data HTTP 429; Bybit `retCode 10006`; Binance HTTP 429/418).                 |
| `BrokerError`                 | Any other adapter-level/transport error (e.g. gRPC `30014` for an overly wide explicit T-Bank intraday window). |

All of these except `ValueError` come from
[`src/broker_adapter/base.py`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/src/broker_adapter/base.py).

---

## Examples

### 1. Fetch by days (default source)

```python
from examples.tbank_adapter_usage import run_fetch_candles

candles = run_fetch_candles(instrument="GAZP", timeframe="1h", days=14)
```

### 2. Twelve Data explicitly

```python
from examples.tbank_adapter_usage import run_fetch_candles

# Daily candles for Apple
candles = run_fetch_candles(
    instrument="AAPL",
    source="twelvedata",
    timeframe="1d",
    days=60,
)

# Forex pair
candles = run_fetch_candles(
    instrument="EUR/USD",
    source="twelvedata",
    timeframe="1h",
    days=7,
)
```

### 3. Bybit explicitly

```python
from examples.tbank_adapter_usage import run_fetch_candles

# Daily candles for BTC/USDT (spot). No token required.
candles = run_fetch_candles(
    instrument="BTCUSDT",
    source="bybit",
    timeframe="1d",
    days=60,
)

# Intraday — the adapter paginates past Bybit's 200-candle cap automatically
candles = run_fetch_candles(
    instrument="ETHUSDT",
    source="bybit",
    timeframe="1m",
    days=1,  # ~1440 one-minute candles
)
```

### 4. Binance explicitly

```python
from examples.tbank_adapter_usage import run_fetch_candles

# Daily candles for ETH/BTC (spot). No token required.
candles = run_fetch_candles(
    instrument="ETHBTC",
    source="binance",
    timeframe="1d",
    days=60,
)

# Fiat-quoted stablecoin pair (FX-like)
candles = run_fetch_candles(
    instrument="EURUSDT",
    source="binance",
    timeframe="1h",
    days=7,
)

# Intraday — the adapter paginates past Binance's 1000-candle cap automatically
candles = run_fetch_candles(
    instrument="BTCUSDT",
    source="binance",
    timeframe="1m",
    days=1,  # ~1440 one-minute candles
)
```

### 5. Set the default source via `.env`

```dotenv
# .env
TWELVEDATA_TOKEN=...
DATA_SOURCE=twelvedata
```

```python
# source= is now optional; DATA_SOURCE is used
candles = run_fetch_candles(instrument="AAPL", timeframe="1d", days=30)
```

### 6. Fetch an explicit window

```python
candles = run_fetch_candles(
    instrument="LKOH",
    timeframe="1d",
    from_date="2024-01-01",
    to_date="2024-06-30",
)
```

### 7. Use the T-Bank sandbox

```python
candles = run_fetch_candles(
    instrument="SBER",
    source="tbank",
    timeframe="5m",
    days=1,
    use_sandbox=True,
)
```

### 8. Async usage

```python
import asyncio
from examples.tbank_adapter_usage import fetch_candles

async def main():
    return await fetch_candles(
        instrument="AAPL", source="twelvedata", timeframe="1h", days=7
    )

candles = asyncio.run(main())
```

### 9. Run a backtest

```python
from examples.tbank_adapter_usage import run_backtest

result = run_backtest(
    instrument="AAPL",
    source="twelvedata",
    timeframe="1d",
    days=120,
    initial_capital=100_000,
    strategy_params={"fast": 10, "slow": 30, "order_size": 1.0},
)
print(result["candles_count"], "candles ->", len(result["trade_log"]), "trades")
```

### 10. Minimum timeframe (1 minute)

```python
candles = run_fetch_candles(instrument="SBER", timeframe="1m", days=1)

# Sub-minute requests are rejected:
# run_fetch_candles(instrument="SBER", timeframe="30s", days=1)
# -> ValueError: the minimum supported resolution is '1m' (1 minute)...
```

---

## Limitations

- **T-Bank history window is capped per timeframe** in the sandbox — intraday
  timeframes (`1m`–`1h`) return *nothing* past their cap (gRPC `30014`). See
  [history limits](#history-limits-days). For longer intraday history, split
  the request into multiple ≤-cap windows or use a coarser timeframe. Twelve
  Data has no such per-timeframe cap (only a soft 3650-day ceiling).
- **`days` validation only applies when `from_date` is not supplied.** An
  explicit `from_date`/`to_date` window is sent as-is; an overly wide T-Bank
  intraday range will return an empty list (no exception).
- **Twelve Data rate limits** depend on your plan (free tier is ~8 requests/min,
  with a daily credit allowance). For bulk fetches, throttle your calls.
- **Binance rate limits** apply per-IP and per-API-key (a request-weight budget
  per rolling minute). Hitting the limit returns HTTP `429`; continuing past
  it can trigger an automatic IP ban (HTTP `418`) lasting from a few minutes
  to several days. For bulk fetches, throttle your calls. The kline endpoint is
  comparatively cheap (weight 1–2 per request) — see the
  [Binance docs](https://developers.binance.com/docs/binance-spot-api-docs/rest-api)
  for current weights.
- **No real orders / portfolio access.** All adapters' `place_order()` and
  `get_portfolio()` raise `NotImplementedError` — this module is read-only for
  market data.
- **SSL verification is disabled** (`verify_ssl=False`) for the T-Bank adapter
  in the example for convenience in dev/test. Re-enable certificate
  verification before any production use. (Twelve Data, Bybit, and Binance use
  plain HTTPS and do not disable verification.)
- Results are **historical market data**, not financial advice and not evidence
  of future profitability.
