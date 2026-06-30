# Examples — T-Bank Adapter Usage

This folder contains ready-to-run examples for the **T-Bank Invest API** adapter.
The main entry point is [`tbank_adapter_usage.py`](./tbank_adapter_usage.py), which
provides a thin, friendly wrapper around the low-level
[`TBankAdapter`](../src/broker_adapter/tbank.py) for fetching historical market
candles (OHLC/V) and running simple backtests.

> The file's primary purpose is **parsing/fetching data from the T-Bank Invest API**
> (production or sandbox). All candle-fetching logic goes through the
> `run_fetch_candles` function (synchronous) or `fetch_candles` (async).

---

## Table of contents

1. [Prerequisites](#prerequisites)
2. [Quick start](#quick-start)
3. [Public functions](#public-functions)
4. [`run_fetch_candles` / `fetch_candles` parameters](#run_fetch_candles--fetch_candles-parameters)
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

1. **A T-Bank Invest API token.** Generate one in the T-Bank Invest app or via the
   [API console](https://www.tbank.ru/about/business/ita/invest-api/). For read-only
   candle data a *read-only* token is sufficient and recommended.
2. **A `.env` file** in the project root with the token:

   ```dotenv
   TINKOFF_TOKEN=your_token_here
   ```

   The module loads `.env` automatically on import (`dotenv`), so normally you do not
   pass the token explicitly.
3. **Dependencies installed** (`aiohttp`, `python-dotenv`, protobuf, etc.) — see the
   project [`requirements.txt`](../requirements.txt).

---

## Quick start

```python
from examples.tbank_adapter_usage import run_fetch_candles

# Fetch the last 7 days of 1-hour candles for SBER
candles = run_fetch_candles(
    instrument="SBER",
    timeframe="1h",
    days=7,
)

print(f"Fetched {len(candles)} candles")
for c in candles[:3]:
    print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}")
```

Running the file directly executes two built-in demos (fetch + backtest):

```bash
python examples/tbank_adapter_usage.py
```

---

## Public functions

| Function           | Type   | Description                                                     |
|--------------------|--------|-----------------------------------------------------------------|
| `run_fetch_candles` | sync  | Fetch historical candles. **Main entry point for data parsing.** |
| `fetch_candles`     | async | Underlying coroutine awaited by `run_fetch_candles`.            |
| `run_backtest`      | sync  | Fetch candles and run the MA-Crossover backtest on them.         |
| `get_token`         | sync  | Helper that reads `TINKOFF_TOKEN` from the environment.          |

---

## `run_fetch_candles` / `fetch_candles` parameters

Both functions share the same signature:

```python
run_fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    from_date: Optional[str] = None,   # "YYYY-MM-DD"
    to_date: Optional[str] = None,     # "YYYY-MM-DD"
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> List[Candle]
```

| Parameter     | Type             | Default   | Description                                                                                       |
|---------------|------------------|-----------|---------------------------------------------------------------------------------------------------|
| `instrument`  | `str`            | `"SBER"`  | Ticker (e.g. `"SBER"`, `"GAZP"`, `"LKOH"`) or a 12-char FIGI / `BBG…` identifier. See [tickers](#instrument-tickers). |
| `timeframe`   | `str`            | `"1h"`    | Candle granularity. **Minimum resolution is `1m`.** See [timeframes](#timeframe).                |
| `days`        | `int`            | `7`       | History depth in days, counting back from `to_date`/now. Ignored if `from_date` is given. **Capped per timeframe** — see [history limits](#history-limits-days). |
| `from_date`   | `Optional[str]`  | `None`    | Start date `YYYY-MM-DD`. Overrides `days`.                                                         |
| `to_date`     | `Optional[str]`  | `None`    | End date `YYYY-MM-DD`. Defaults to *now*.                                                          |
| `use_sandbox` | `bool`           | `False`   | Use the T-Bank **sandbox** host instead of the production host.                                    |
| `token`       | `Optional[str]`  | `None`    | API token. If omitted, loaded from `TINKOFF_TOKEN` in `.env` via `get_token()`.                    |

> **`from_date` overrides `days`.** If you pass both, `days` is ignored.
> If you pass neither `from_date` nor `to_date`, the window is `[now - days, now]`.

### Instrument (tickers)

The adapter accepts any ticker listed in the **TQBR** trading mode of MOEX
(Moscow Exchange). Tickers are passed by their standard short symbol:

| Ticker  | Issuer                    | Ticker  | Issuer                    |
|---------|---------------------------|---------|---------------------------|
| `SBER`  | Сбербанк                  | `GMKN`  | Норникель                 |
| `GAZP`  | Газпром                   | `YDEX`  | Яндекс                    |
| `LKOH`  | Лукойл                    | `OZON`  | Ozon                      |
| `ROSN`  | Роснефть                  | `MGNT`  | Магнит                    |
| `NVTK`  | Новатэк                   | `MTSS`  | МТС                       |
| `TATN`  | Татнефть                  | `CHMF`  | Северсталь                |
| `VTBR`  | ВТБ                       | `NLMK`  | НЛМК                      |
| `MGNT`  | Магнит                    | `ALRS`  | Алроса                    |
| `PLZL`  | Полюс                     | `MOEX`  | Московская биржа          |
| `AFKS`  | Sistema                   | `RUAL`  | РУСАЛ                     |

The list above is illustrative, not exhaustive — any TQBR ticker the T-Bank API
knows about will work. The adapter resolves the ticker to a FIGI automatically.
If you already have a FIGI, you can pass it directly: any value starting with
`BBG` or exactly 12 characters long is treated as a FIGI and looked up as-is.

A ticker that the API cannot resolve raises `InvalidInstrumentError`.

### Timeframe

| Value  | Meaning   | Max `days` (sandbox) | Notes                                            |
|--------|-----------|----------------------|--------------------------------------------------|
| `1m`   | 1 minute  | 1                    | **Minimum supported resolution.**                |
| `5m`   | 5 minutes | 7                    |                                                  |
| `15m`  | 15 minutes| 24                   |                                                  |
| `30m`  | 30 minutes| 25                   |                                                  |
| `1h`   | 1 hour    | 100                  |                                                  |
| `1d`   | 1 day     | 365                  | bounded by available history, not by 30014       |
| `1w`   | 1 week    | 365                  | bounded by available history, not by 30014       |
| `1M`   | 1 month   | 365                  | bounded by available history, not by 30014       |

- **Minimum timeframe is `1m`.** Sub-minute intervals (`1s`, `30s`, `15s`, …)
  are **rejected** with a `ValueError` before any network call — the T-Bank
  candle endpoint does not serve finer granularity.
- The supported set is exported as `TIMEFRAMES`; the minimum is exported as
  `MIN_TIMEFRAME = "1m"`.
- Unknown values (e.g. `"2m"`, `"hour"`) are also rejected.
- Surrounding whitespace is tolerated and stripped.

### History limits (`days`)

The T-Bank sandbox's `GetCandles` endpoint caps how wide a date range it will
serve. For **intraday** timeframes, a range that is too wide fails with gRPC
error `30014` and returns **no candles at all**. So the `days` parameter is
validated up front against a per-timeframe cap, and an oversized request raises
a `ValueError` instead of an empty response.

The caps are measured empirically (see the method below) and exported as
`DAYS_LIMIT_BY_TIMEFRAME`:

```python
DAYS_LIMIT_BY_TIMEFRAME = {
    "1m": 1,    "5m": 7,    "15m": 24,   "30m": 25,
    "1h": 100,  "1d": 365,  "1w": 365,   "1M": 365,
}
```

- Intraday limits (`1m`–`1h`) are hard: one day more than the cap → `30014`,
  zero candles. The validator triggers just under the measured boundary.
- Day/week/month limits are **not** caused by `30014` (those timeframes serve
  wide ranges fine); they are a safety bound on available history.
- **Note:** `days` is only validated when `from_date` is *not* supplied (i.e.
  when the window is derived from `days`). If you pass explicit `from_date` /
  `to_date`, the window is sent to the API as-is, and an overly wide intraday
  range will come back empty.

**How the limits were measured.** For each timeframe, an exponential-then-binary
search probed the sandbox for the largest `days` that still returns a non-empty
candle list for `SBER`, while retrying on transient rate-limit errors so
throttling was not misread as a width limit. The boundary where the response
flips from "candles" to gRPC error `30014` is the cap. The validation values
sit just inside those boundaries. Re-run such a probe if the sandbox changes.

### Date range

- Format: `"YYYY-MM-DD"` (parsed strictly via `datetime.strptime`).
- If `to_date` is omitted it defaults to the current moment (`datetime.now()`).
- If `from_date` is omitted it is computed as `to_date - days`; in that case
  `days` is validated against the [history limits](#history-limits-days).
- If `from_date` is supplied explicitly, it overrides `days` and the window is
  not pre-validated for width — an overly wide intraday range returns an empty
  list from the API (no exception).

### Environment & token

- `use_sandbox=False` (default) → `https://invest-public-api.tbank.ru`.
- `use_sandbox=True`  → `https://sandbox-invest-public-api.tbank.ru`.
  Use the sandbox for testing without touching real account endpoints.
- `token=None` (default) → loaded from the `TINKOFF_TOKEN` environment variable
  via `get_token()`, which raises a clear `ValueError` if the variable is unset.

---

## Return format

Both `fetch_candles` and `run_fetch_candles` return a `List[Candle]` in
**chronological order** (oldest first). `Candle` is the unified dataclass from
[`src/engine/models.py`](../src/engine/models.py):

```python
@dataclass
class Candle:
    timestamp: str   # ISO-8601 without tz: "YYYY-MM-DDTHH:MM:SS" (UTC)
    open:     float  # OHLC are prices in the instrument's currency (usually RUB)
    high:     float
    low:      float
    close:    float
    volume:    float  # traded volume for the candle's interval
```

- **`timestamp`** is a string in `"YYYY-MM-DDTHH:MM:SS"` format and represents
  the candle's **start time in UTC** (the API returns UTC).
- **`open/high/low/close`** are floats converted from the API's
  `Quotation` (units + nano) representation, preserving full precision.
- **`volume`** is a float (cast from the integer the API returns).
- The list is returned in the order the API provides (chronological, oldest
  first). It is **not** post-validated — the adapter passes candles through
  unchanged.

You can iterate the list directly, or hand it to any component that expects
`List[Candle]` — e.g. `ExecutionEngine.run(...)`.

---

## Validation rules

The module validates user **inputs** before any network call. Both checks raise
`ValueError` with a descriptive message:

1. **Timeframe** (`_validate_timeframe`)
   - Must be one of `TIMEFRAMES`.
   - Sub-minute intervals (`*s`) are explicitly rejected — minimum is `1m`.

2. **History depth** (`_validate_days`), checked only when the window is derived
   from `days` (i.e. `from_date` not supplied):
   - `days` must be a positive integer.
   - `days` must not exceed the per-timeframe cap in `DAYS_LIMIT_BY_TIMEFRAME`
     (see [history limits](#history-limits-days)).

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
the `MACrossover` strategy. Pass the same timeframe/instrument validation rules
apply (minimum `1m`).

---

## Errors and exceptions

| Exception                     | When it is raised                                                                 |
|-------------------------------|-----------------------------------------------------------------------------------|
| `ValueError`                  | Unsupported/`sub-1m` `timeframe`, or `days` larger than the per-timeframe cap (`DAYS_LIMIT_BY_TIMEFRAME`). |
| `ValueError` (from `get_token`)| `TINKOFF_TOKEN` is not set in the environment and no `token=` was passed.        |
| `AuthenticationError`         | The token is invalid/expired (gRPC status 16) or connection test fails.          |
| `InvalidInstrumentError`      | The ticker cannot be resolved to a FIGI by the API.                              |
| `RateLimitError`              | T-Bank rate limit hit (gRPC status 8).                                            |
| `BrokerError`                 | Any other adapter-level/gRPC/transport error (e.g. gRPC `30014` if an explicit `from_date`/`to_date` window is too wide for an intraday timeframe). |

All of these except `ValueError` come from
[`src/broker_adapter/base.py`](../src/broker_adapter/base.py).

---

## Examples

### 1. Fetch by days

```python
from examples.tbank_adapter_usage import run_fetch_candles

candles = run_fetch_candles(instrument="GAZP", timeframe="1h", days=14)
```

### 2. Fetch an explicit window

```python
candles = run_fetch_candles(
    instrument="LKOH",
    timeframe="1d",
    from_date="2024-01-01",
    to_date="2024-06-30",
)
```

### 3. Use the sandbox

```python
candles = run_fetch_candles(
    instrument="SBER",
    timeframe="5m",
    days=1,
    use_sandbox=True,
)
```

### 4. Async usage

```python
import asyncio
from examples.tbank_adapter_usage import fetch_candles

async def main():
    return await fetch_candles(instrument="SBER", timeframe="1h", days=7)

candles = asyncio.run(main())
```

### 5. Run a backtest

```python
from examples.tbank_adapter_usage import run_backtest

result = run_backtest(
    instrument="SBER",
    timeframe="1h",
    days=30,
    initial_capital=100_000,
    strategy_params={"fast": 10, "slow": 30, "order_size": 1.0},
)
print(result["candles_count"], "candles ->", len(result["trade_log"]), "trades")
```

### 6. Minimum timeframe (1 minute)

```python
candles = run_fetch_candles(instrument="SBER", timeframe="1m", days=1)

# Sub-minute requests are rejected:
# run_fetch_candles(instrument="SBER", timeframe="30s", days=1)
# -> ValueError: the minimum supported resolution is '1m' (1 minute)...
```

---

## Limitations

- **History window is capped per timeframe** in the sandbox — intraday
  timeframes (`1m`–`1h`) return *nothing* past their cap (gRPC `30014`). See
  [history limits](#history-limits-days). For longer intraday history, split
  the request into multiple ≤-cap windows or use a coarser timeframe.
- **`days` validation only applies when `from_date` is not supplied.** An
  explicit `from_date`/`to_date` window is sent as-is; an overly wide intraday
  range will return an empty list (no exception).
- **No real orders / portfolio access.** `TBankAdapter.place_order()` and
  `get_portfolio()` raise `NotImplementedError` — this module is read-only for
  market data.
- **SSL verification is disabled** (`verify_ssl=False`) in the example for
  convenience in dev/test. Re-enable certificate verification before any
  production use.
- Results are **historical market data**, not financial advice and not evidence
  of future profitability.
