# Broker-Independent Abstraction Layer

The abstraction layer provides unified access to market data and trading operations, hiding the implementation details of a specific broker (T-Bank Invest API, others). This makes it easy to replace the broker or add new ones without changing the core analysis and strategy logic.

## 1.1 Interface `BrokerAdapter`

The interface defines the contract that every concrete broker adapter must implement.

**Methods:**

- **`get_candles(instrument: str, timeframe: str, from_dt: datetime, to_dt: datetime) -> List[Candle]`**  
  Retrieves historical candles for the instrument over the specified period.
  - *Parameters*: instrument (ticker), timeframe (1min, 5min, hour, day, etc.), start (`from_dt`) and end (`to_dt`) dates.
  - *Returns*: a list of `Candle` models.

- **`place_order(instrument: str, action: str, quantity: float, price: Optional[float] = None) -> OrderResult`**  
  Places a trading order (buy/sell).
  - *Parameters*: instrument, action (buy/sell), quantity, price (optional, for limit orders).
  - *Returns*: an `OrderResult` structure with order ID, status, executed price, etc.

- **`get_portfolio(account_id: str) -> Portfolio`**  
  Retrieves the client's current portfolio.
  - *Parameters*: account identifier (optional).
  - *Returns*: a `Portfolio` structure with a list of positions (asset, quantity, average price, current value, etc.).

## 1.2 Common `Candle` model

The candle model used throughout the system (both for retrieving from the broker and for passing to analysis modules).

| Field        | Type         | Description                                      |
|--------------|--------------|--------------------------------------------------|
| `instrument` | str          | Instrument ticker (e.g., AAPL)                   |
| `timestamp`  | datetime     | Candle start time (UTC)                          |
| `timeframe`  | str          | Candle timeframe (1m, 5m, 1h, 1d)               |
| `open`       | float        | Opening price                                    |
| `high`       | float        | Highest price during the period                  |
| `low`        | float        | Lowest price during the period                   |
| `close`      | float        | Closing price                                    |
| `volume`     | int/float    | Trading volume (number of shares/contracts)      |

Optionally, an `adjusted_close` field may be included to account for corporate actions (splits, dividends). The model must be serializable to JSON and compatible with Pandas DataFrame for analysis.

## 1.3 API Contracts reviewed with Data Loader

The API contracts between `BrokerAdapter` and the `Data Loader` module (responsible for loading data into the system) must be reviewed and approved. Key requirements:

- **Data formats**: all exchanges use strictly typed models (Pydantic or dataclasses).  
- **Error handling**: standardized exceptions (e.g., `RateLimitError`, `InvalidInstrumentError`).  
- **Asynchronicity**: adapter methods assume asynchronous calls (async/await) for efficient network requests.  
- **Pagination**: methods returning lists (especially `get_candles`) support pagination via `limit` and `offset` parameters or cursors.  
- **Caching**: caching of candles is allowed at the Data Loader level to reduce broker API load. The contract specifies that the adapter is not responsible for caching, only for reading "raw" data.

The contract is considered finalized once a set of integration tests against a mock adapter and a test broker passes without errors.
