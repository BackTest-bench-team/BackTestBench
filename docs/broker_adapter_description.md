# Broker Adapter

Last audited against `main`: **June 30, 2026**.

## Purpose

`BrokerAdapter` defines an asynchronous boundary for market data and future trading
operations. The current integrated pipeline uses only historical candle retrieval from
T-Bank.

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

- `place_order()` raises `NotImplementedError`;
- `get_portfolio()` raises `NotImplementedError`;
- `csv_adapter.py` is empty;
- `offset` is unused;
- `limit` only slices the returned list after one request;
- large ranges are not split into broker-safe windows;
- `DataLoader` reuses SQLite candles when the lookback window is covered; otherwise
  `main.py` fetches from T-Bank and upserts into `data/backtest.db`;
- `connect()` validates the session by requesting SBER specifically;
- `verify_ssl` defaults to `False`, and `main.py` explicitly disables certificate
  verification. Production use must enable verification.

## Error Types

- `BrokerError`;
- `AuthenticationError`;
- `InvalidInstrumentError`;
- `RateLimitError`;
- `InsufficientFundsError` (defined, not used by current adapter);
- `InvalidAccountError` (defined, not used by current adapter).

## Environment

```dotenv
TINKOFF_TOKEN=your_token_here
```

Never commit token values. The integrated dashboard and Docker Compose require a root
`.env` file.

## Current Data Flow

```text
main.py
  -> DataLoader.db_candles_usable() ?
       yes -> load from SQLite (data/backtest.db)
       no  -> TBankAdapter.get_candles(...) -> DataLoader.store_candles()
  -> list[engine.Candle]
  -> ExecutionEngine (per strategy)
```

CSV fallback, multi-broker selection, order placement, and portfolio retrieval are future work.
