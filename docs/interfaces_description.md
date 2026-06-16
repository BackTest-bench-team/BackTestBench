# interfaces.py — Module Contracts

This document describes every shared type defined in `interfaces.py`: what it represents, which module produces it, which module consumes it, and what each field means.

**Rule:** no module imports another module directly. All cross-module communication happens through these types.
---

## Overview — who uses what

| Type | Produced by | Consumed by |
|---|---|---|
| `Candle` | Broker Adapter (via Data Loader) | Data Loader, Simulation Engine |
| `Signal` | Strategy Module | Simulation Engine |
| `Trade` | Simulation Engine | (part of TradeLog) |
| `TradeLog` | Simulation Engine | Analytics Module |
| `MetricsReport` | Analytics Module | Database, Frontend |
| `OrderResult` | Broker Adapter | Trading Bot |
| `BrokerAdapter` (ABC) | implemented by Broker Adapter module | used by Data Loader, Trading Bot |
| `BaseStrategy` (ABC) | implemented by Strategy Module | used by Simulation Engine |

---

## Enums

### `ActionType`

Possible actions a strategy can signal for a given candle.

| Value | Meaning |
|---|---|
| `BUY` | Open or increase a long position |
| `SELL` | Close or decrease a position |
| `HOLD` | Do nothing on this candle |

Used inside `Signal.action` and as a parameter to `BrokerAdapter.place_order()`.

---

### `OrderStatus`

Result status of an order placement attempt.

| Value | Meaning |
|---|---|
| `FILLED` | Order was executed |
| `REJECTED` | Order was not accepted by the broker |
| `PENDING` | Order is still being processed |

Used inside `OrderResult.status`.

---

## `Candle`

A single OHLCV candle for one instrument and timeframe.

**Produced by:** Broker Adapter (`get_candles()`), cached and normalized by Data Loader.
**Consumed by:** Data Loader (stores in DB), Simulation Engine (iterates over `List[Candle]`).

| Field | Type | Description |
|---|---|---|
| `instrument` | `str` | Ticker or instrument identifier, e.g. `"SBER"`, `"OIL"` |
| `timeframe` | `str` | Candle interval, e.g. `"1m"`, `"1h"`, `"1d"` |
| `timestamp` | `datetime` | Open time of the candle (UTC) |
| `open` | `float` | Opening price |
| `high` | `float` | Highest price during the candle |
| `low` | `float` | Lowest price during the candle |
| `close` | `float` | Closing price |
| `volume` | `float` | Traded volume during the candle |

**Where it flows:**
```
Broker Adapter.get_candles() → List[Candle] → Data Loader → DB
DB → List[Candle] → Simulation Engine
```

---

## `Signal`

Output of a strategy's decision for a single candle.

**Produced by:** any `BaseStrategy.on_candle()` implementation.
**Consumed by:** Simulation Engine — used to decide whether to open/close a position.

| Field | Type | Default | Description |
|---|---|---|---|
| `action` | `ActionType` | — | `BUY`, `SELL`, or `HOLD` |
| `quantity` | `float` | `0.0` | Size of the position to open/close. Ignored for `HOLD` |
| `reason` | `str` | `""` | Human-readable explanation, e.g. `"RSI crossed above 70"`. Used for debugging and trade log readability |

**Where it flows:**
```
Simulation Engine calls strategy.on_candle(candle, portfolio) → Signal
Simulation Engine uses Signal to simulate order execution → Trade
```

---

## `Trade`

A single completed trade produced during simulation.

**Produced by:** Simulation Engine, as part of `TradeLog.trades`.
**Consumed by:** Analytics Module (via `TradeLog`).

| Field | Type | Description |
|---|---|---|
| `instrument` | `str` | Instrument the trade was executed on |
| `entry_price` | `float` | Price at which the position was opened |
| `exit_price` | `float` | Price at which the position was closed |
| `quantity` | `float` | Size of the position |
| `pnl` | `float` | Profit or loss for this trade (account currency) |
| `opened_at` | `datetime` | Timestamp when the position was opened |
| `closed_at` | `datetime` | Timestamp when the position was closed |

---

## `TradeLog`

Full record of all trades produced by a single simulation run.

**Produced by:** Simulation Engine, at the end of a backtest run.
**Consumed by:** Analytics Module (computes `MetricsReport`), persisted to DB (`backtest_runs` / `trades` tables).

| Field | Type | Default | Description |
|---|---|---|---|
| `strategy_id` | `str` | — | Identifier of the strategy that produced these trades |
| `instrument` | `str` | — | Instrument the simulation was run on |
| `trades` | `List[Trade]` | `[]` | Ordered list of completed trades |
| `final_portfolio_value` | `float` | `0.0` | Portfolio value at the end of the run |

**Where it flows:**
```
Simulation Engine → TradeLog → Analytics Module → MetricsReport
Simulation Engine → TradeLog → DB (trades table)
```

---

## `MetricsReport`

Performance metrics computed from a `TradeLog`.

**Produced by:** Analytics Module.
**Consumed by:** DB (`metrics` table), Frontend (dashboard), top-N ranking logic.

| Field | Type | Description |
|---|---|---|
| `strategy_id` | `str` | Identifier of the strategy these metrics belong to |
| `instrument` | `str` | Instrument the metrics were computed for |
| `total_pnl` | `float` | Sum of profit/loss across all trades |
| `sharpe_ratio` | `float` | Risk-adjusted return measure |
| `max_drawdown` | `float` | Largest peak-to-trough decline, as a positive fraction (e.g. `0.15` = 15%) |
| `win_rate` | `float` | Fraction of profitable trades, `0.0`–`1.0` |
| `deposit_baseline_pnl` | `float` | Reference P&L if the same capital had earned the baseline deposit rate (13% annual) over the same period — used to compare against `total_pnl` |

**Where it flows:**
```
Analytics Module → MetricsReport → DB (metrics table)
DB → MetricsReport → Frontend (dashboard)
DB → List[MetricsReport] → Analytics ranking logic → top-N list
```

---

## `OrderResult`

Result of an order placement attempt via a `BrokerAdapter`.

**Produced by:** `BrokerAdapter.place_order()`.
**Consumed by:** Trading Bot (to record validation trades).

| Field | Type | Default | Description |
|---|---|---|---|
| `order_id` | `Optional[str]` | `None` | Broker-assigned order identifier; `None` if the order was rejected before placement |
| `status` | `OrderStatus` | — | `FILLED`, `REJECTED`, or `PENDING` |
| `filled_price` | `Optional[float]` | `None` | Price at which the order was filled, if applicable |
| `filled_quantity` | `Optional[float]` | `None` | Quantity actually filled, if applicable |
| `message` | `str` | `""` | Human-readable detail, e.g. an error message on rejection |

---

## `BrokerAdapter` (ABC)

Unified interface to a market data source and/or broker. Implemented by concrete adapters (`TBankAdapter`, `CSVAdapter`).

**Implemented by:** Broker Adapter module.
**Used by:** Data Loader (for historical data), Trading Bot (for order execution).

**Why it exists:** when the broker changes, only the adapter implementation changes — Data Loader, Simulation Engine, and Trading Bot never need to change.

**Async contract:** all methods are `async` — implementations must use `async/await`. Callers must `await` every call.

### `get_candles(instrument, from_dt, to_dt, timeframe) -> List[Candle]`

Fetch historical candles for the given instrument and date range.

| Parameter | Type | Description |
|---|---|---|
| `instrument` | `str` | Ticker or instrument identifier |
| `from_dt` | `datetime` | Start of requested range (inclusive, UTC) |
| `to_dt` | `datetime` | End of requested range (exclusive, UTC) |
| `timeframe` | `str` | Candle interval, e.g. `"1m"`, `"1h"`, `"1d"` |

**Returns:** `List[Candle]`, ordered chronologically. Empty list if no data available.

**Called by:** Data Loader. The requested range depends on context — explicit historical period for backtesting, or `last_sync_timestamp → now` for Scheduler updates.

---

### `place_order(instrument, action, quantity, price=None) -> OrderResult`

Place an order with the broker (or simulated sandbox).

| Parameter | Type | Description |
|---|---|---|
| `instrument` | `str` | Ticker or instrument identifier |
| `action` | `ActionType` | `BUY` or `SELL`. `HOLD` is invalid here |
| `quantity` | `float` | Size of the order |
| `price` | `Optional[float]` | Limit price; `None` for market orders |

**Returns:** `OrderResult` describing the outcome.

**Called by:** Trading Bot.

---

### `get_portfolio() -> Portfolio`

Retrieve current portfolio state from the broker.

**Returns:** `Portfolio` describing holdings and cash balance.

**Called by:** Trading Bot, Simulation Engine (for virtual portfolio state).

---

## `Portfolio`

Current portfolio state returned by `BrokerAdapter.get_portfolio()`.

**Produced by:** `BrokerAdapter.get_portfolio()`.
**Consumed by:** Trading Bot, Simulation Engine.

| Field | Type | Default | Description |
|---|---|---|---|
| `cash` | `float` | — | Available cash balance (account currency) |
| `positions` | `List[dict]` | `[]` | List of open positions. Each entry contains `instrument` (str), `quantity` (float), `avg_price` (float). Shape may vary per adapter; callers should not rely on extra keys |

---

## `BaseStrategy` (ABC)

Common interface for all trading strategies. Every strategy is an independent plugin configured via YAML.

**Implemented by:** Strategy Module (one subclass per strategy, e.g. `MACrossover`, `RSIStrategy`).
**Used by:** Simulation Engine.

### `__init__(self, params: dict)`

| Parameter | Type | Description |
|---|---|---|
| `params` | `dict` | Parameters loaded from the strategy's YAML config (indicator periods, thresholds, filters, risk limits) |

---

### `on_candle(self, candle: Candle, portfolio: dict) -> Signal`

Decide what action to take given a new candle and current portfolio.

| Parameter | Type | Description |
|---|---|---|
| `candle` | `Candle` | The latest candle received by the simulation |
| `portfolio` | `dict` | Current virtual portfolio state (cash, open positions) as maintained by Simulation Engine |

**Returns:** `Signal` — `BUY`/`SELL`/`HOLD` with quantity and optional reason.

**Called by:** Simulation Engine, once per candle, for every registered strategy.

**Key property:** Simulation Engine calls this method identically for every strategy — it never inspects strategy internals. This is what allows new strategies to be added without modifying the core engine.

---

## End-to-end data flow (backtest)

```
1. Broker Adapter.get_candles(instrument, from_dt, to_dt, timeframe)
       → List[Candle]

2. Data Loader caches/validates/normalizes
       → List[Candle] persisted to DB

3. Simulation Engine, for each Candle:
       strategy.on_candle(candle, portfolio) → Signal
       Signal → simulated order execution → updates portfolio
       → accumulates Trade objects

4. Simulation Engine, at end of run:
       → TradeLog (strategy_id, instrument, trades, final_portfolio_value)

5. Analytics Module:
       TradeLog → MetricsReport (total_pnl, sharpe_ratio, max_drawdown,
                                   win_rate, deposit_baseline_pnl)
       → persisted to DB (metrics table)

6. Analytics Module (ranking):
       List[MetricsReport] → filter by deposit_baseline_pnl
                            → sort by total_pnl
                            → top-N list → DB
```

## End-to-end data flow (validation / Trading Bot)

```
1. Trading Bot reads top-N list from DB

2. For each top-N strategy:
       Broker Adapter.get_candles(...) → reserved fresh data
       Simulation Engine + strategy.on_candle() → TradeLog (validation)

3. Analytics Module:
       TradeLog → MetricsReport (validation)
       → persisted to DB
```