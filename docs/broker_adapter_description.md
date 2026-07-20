# Broker Adapter

Last audited against `main`: **July 19, 2026**.

## Purpose

`BrokerAdapter` defines an asynchronous boundary for market data and future trading
operations. The dashboard and Live refresh select a concrete
adapter through `src/broker_adapter/factory.py` (`build_adapter`).

## Factory Sources

`SUPPORTED_SOURCES`: `tbank`, `twelvedata`, `bybit`, `binance`.

| Source | Env token | Notes |
|---|---|---|
| `tbank` | `TINKOFF_TOKEN` | MOEX/TQBR historical candles; optional sandbox host |
| `twelvedata` | `TWELVEDATA_TOKEN` | REST `/time_series` |
| `bybit` | `BYBIT_TOKEN` (optional for some public endpoints) | V5 kline API |
| `binance` | `BINANCE_TOKEN` (optional for some public endpoints) | Added PR #145 |

Display names and token status are also used by `GET/POST /api/tokens`.

## Interface

```python
class BrokerAdapter(ABC):
    async def get_candles(
        self,
        instrument: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> list[Candle]: ...

    async def place_order(
        self,
        instrument: str,
        action: str,
        quantity: float,
        price: Optional[float] = None,
    ) -> OrderResult: ...

    async def get_portfolio(
        self,
        account_id: Optional[str] = None,
    ) -> Portfolio: ...

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
```

The base class supports `async with adapter`.

## T-Bank Implementation

Implemented in `src/broker_adapter/tbank.py`:

- token loading from constructor or `TINKOFF_TOKEN`;
- production and sandbox host selection;
- async HTTP session lifecycle;
- ticker-to-FIGI lookup for the `TQBR` class;
- gRPC-framed HTTP requests for historical candles;
- quotation conversion from units/nanos to float;
- conversion to `src.engine.models.Candle`;
- authentication, rate-limit, invalid-instrument, and general broker errors.

Supported timeframe keys:

`1m`, `5m`, `15m`, `30m`, `1h`, `1d`, `1w`, `1M`.

## TwelveData Adapter

Implemented in `src/broker_adapter/twelvedata.py` (PR #135):

- REST `/time_series` endpoint;
- token from `TWELVEDATA_TOKEN`;
- returns engine `Candle` list.

Wired into bootstrap and live refresh through the factory.

## Bybit Adapter

Implemented in `src/broker_adapter/bybit.py` (PR #135):

- V5 kline API with 200-candle pagination;
- spot symbol list in `examples/List_of_spots_bybit.txt`;
- returns engine `Candle` list.

Wired into runtime through the factory; examples remain useful for standalone demos.

## Binance Adapter

Implemented in `src/broker_adapter/binance.py` (PR #145):

- historical kline fetch mapped to engine `Candle`;
- registered in `factory.py` as `binance`;
- examples documentation updated in `examples/README.md`.

Note: merge title of PR #145 mentioned T-Bank `place_order` / `get_portfolio`, but those
methods remain stubs (see Current Limitations).

The strategy configuration parser supports a smaller set:
`1m`, `5m`, `15m`, `1h`, `4h`, `1d`. In particular, `4h` is accepted by strategy
configuration but not by `TBankAdapter`, while `30m`, `1w`, and `1M` are accepted by the
adapter but not by strategy configuration. This mismatch is a known issue.

## Candle Shape

The adapter returns the engine candle:

```python
Candle(
    timestamp: str,
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
)
```

Instrument and timeframe are run-level metadata, not candle fields. T-Bank timestamps are
formatted as `YYYY-MM-DDTHH:MM:SS` without an explicit `Z` suffix.

## Current Limitations

- `place_order()` raises `NotImplementedError` on current adapters including T-Bank;
- `get_portfolio()` raises `NotImplementedError`;
- `csv_adapter.py` is empty;
- `offset` is unused;
- `limit` only slices the returned list after one request;
- large ranges are not always split into broker-safe windows;
- `DataLoader` reuses SQLite candles when the lookback window is covered; otherwise the
  selected factory adapter fetches and upserts into `data/backtest.db`;
- T-Bank `connect()` validates the session by requesting SBER specifically;
- `verify_ssl` defaults to `False` for T-Bank; production use must enable verification.

## Error Types

- `BrokerError`;
- `AuthenticationError`;
- `InvalidInstrumentError`;
- `RateLimitError`;
- `InsufficientFundsError` (defined, not used by current adapters);
- `InvalidAccountError` (defined, not used by current adapters).

## Environment

```dotenv
TINKOFF_TOKEN=your_token_here
TWELVEDATA_TOKEN=your_token_here
BYBIT_TOKEN=your_token_here
BINANCE_TOKEN=your_token_here
```

Never commit token values. The integrated dashboard and Docker Compose require a root
`.env` file (tokens may also be written from the UI into that file).

## Current Data Flow

```text
main.py bootstrap / live_run_tick
  -> build_adapter(source)
  -> load_candles_for_backtest() / ensure_backtest_candles()
       cache hit -> SQLite (data/backtest.db)
       miss / force_fetch -> adapter.get_candles(...) chunked -> upsert
  -> list[engine.Candle]
  -> ExecutionEngine.run(...)
```

Order placement and portfolio retrieval remain future work. Live trading automation is out
of scope; the dashboard simulates fills only.
