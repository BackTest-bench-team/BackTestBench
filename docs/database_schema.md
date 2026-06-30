# Database Schema (MVP1)

> **Status as of June 30, 2026:** hybrid implementation. The **`candles`** table is
> operational in SQLite (`data/backtest.db`) via `src/db/models.py` (`CandleModel`) and
> `src/data_loader/loader.py`. Relational tables for strategies, backtest runs, trades, and
> metrics remain **target schema only**. The integrated pipeline stores the latest multi-strategy
> dashboard state in `data/runtime-dashboard.json`.

The project requires storage of historical data, strategy configurations, and backtesting
results. Below is the relational schema (SQLite/PostgreSQL) with entities and relationships
for the first development phase (MVP1).

> **Note on SQL types:** attribute definitions use PostgreSQL syntax (`SERIAL`, `DECIMAL`,
> `TEXT`). For SQLite use `INTEGER PRIMARY KEY` instead of `SERIAL PK` and `REAL` instead of
> `DECIMAL` — SQLite maps these transparently via type affinity.

## Implemented: SQLite Candle Storage

| Entity | Status | Implementation |
|---|---|---|
| **candles** | Implemented | `CandleModel` in `src/db/models.py`; upsert on `(instrument, timeframe, timestamp)` via `DataLoader.store_candles()` |

The Data Loader:

- validates candles before storage (`validate_candles()`);
- normalises broker candles into `CandleModel` rows;
- skips T-Bank fetch when SQLite already covers the requested lookback window;
- optionally uses an in-memory `CandleCache` for hot instrument/timeframe pairs.

Default database URL resolves to `data/backtest.db`. Set `DATABASE_URL` in `.env` to override.

## Target: Relational Run Schema (Not Implemented)

The following entities describe the planned durable run-history store. No SQLAlchemy models,
migrations, or writes exist for these tables today.

## 1.1 Entities and attributes (MVP1)

| Entity            | Attributes (field, type, description)                                                                                                                                                                                                                                                                      | Relationships                                                         |
|-------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **candles**       | `id` SERIAL PK<br>`instrument` VARCHAR(20) NOT NULL<br>`timeframe` VARCHAR(10) NOT NULL<br>`timestamp` TIMESTAMP NOT NULL<br>`open` DECIMAL(12,4)<br>`high` DECIMAL(12,4)<br>`low` DECIMAL(12,4)<br>`close` DECIMAL(12,4)<br>`volume` BIGINT<br>UNIQUE(instrument, timeframe, timestamp)                   | (no foreign keys) — **implemented in SQLite**                         |
| **strategies**    | `id` SERIAL PK<br>`name` VARCHAR(100) UNIQUE NOT NULL<br>`yaml_config` TEXT NOT NULL<br>`created_at` TIMESTAMP DEFAULT NOW()                                                                                                                                                                                | 1 : N → backtest_runs — **planned**                                   |
| **backtest_runs** | `id` SERIAL PK<br>`strategy_id` INT FK → strategies.id<br>`instrument` VARCHAR(20) NOT NULL<br>`from_dt` TIMESTAMP NOT NULL<br>`to_dt` TIMESTAMP NOT NULL<br>`status` VARCHAR(20) (pending, running, completed, failed)                                                                                    | N : 1 → strategies<br>1 : N → trades<br>1 : 1 → metrics (optional) — **planned** |
| **trades**        | `id` SERIAL PK<br>`run_id` INT FK → backtest_runs.id<br>`instrument` VARCHAR(20) NOT NULL<br>`entry_price` DECIMAL(12,4)<br>`exit_price` DECIMAL(12,4)<br>`quantity` DECIMAL(18,8)<br>`pnl` DECIMAL(12,4)<br>`opened_at` TIMESTAMP<br>`closed_at` TIMESTAMP                                               | N : 1 → backtest_runs — **planned**                                   |
| **metrics**       | `id` SERIAL PK<br>`run_id` INT UNIQUE FK → backtest_runs.id<br>`total_pnl` DECIMAL(12,4)<br>`sharpe_ratio` DECIMAL(8,4)<br>`max_drawdown` DECIMAL(8,4)<br>`win_rate` DECIMAL(5,4)<br>`deposit_baseline_pnl` DECIMAL(12,4)                                                                                 | 1 : 1 → backtest_runs — **planned**                                   |

## 1.2 ER diagram

```text
┌──────────────────┐          ┌───────────────────────┐
│    strategies    │          │       candles         │
│──────────────────│          │───────────────────────│
│ id (PK)          │          │ id (PK)               │
│ name             │          │ instrument            │
│ yaml_config      │          │ timeframe             │
│ created_at       │          │ timestamp             │
└──────────────────┘          │ open, high, low,      │
         │                    │ close, volume         │
         │ 1                  └───────────────────────┘
         │                              ▲
         │                              │ implemented (SQLite)
         │ 0..*                  (independent — linked via
         ▼                       instrument and date range
┌────────────────────┐           in backtest_runs)
│   backtest_runs    │          planned — not implemented
│────────────────────│
│ id (PK)            │
│ strategy_id (FK)   │
│ instrument         │
│ from_dt, to_dt     │
│ status             │
└────────────────────┘
         │
         │ 1
         │
         │ 0..*
         ▼
┌────────────────────┐
│       trades       │
│────────────────────│
│ id (PK)            │
│ run_id (FK)        │
│ instrument         │
│ entry_price        │
│ exit_price         │
│ quantity, pnl      │
│ opened_at          │
│ closed_at          │
└────────────────────┘
         │
         │ 1
         │
         │ 0..1
         ▼
┌────────────────────┐
│      metrics       │
│────────────────────│
│ id (PK)            │
│ run_id (UNIQUE FK) │
│ total_pnl          │
│ sharpe_ratio       │
│ max_drawdown       │
│ win_rate           │
│ deposit_baseline_pnl│
└────────────────────┘
```

## 1.3 Implementation Gap (Run History)

Before the relational run schema becomes operational, the project needs:

1. SQLAlchemy models and migrations for strategies, runs, trades, and metrics;
2. persistence from `main.py` or the future API service;
3. run IDs that consistently match the in-memory `RunContext`;
4. storage for per-run equity curves;
5. tests for transactions, foreign keys, numeric precision, and failed-run rollback.

The analytics document also describes future `equity_points` and `top_n` tables. They are
not present in the original MVP1 table list above and should be included in the first
implemented migration if that target design is retained.

In-memory Top-N ranking and validation metrics are implemented in `src/analytics/` and
serialised into `data/runtime-dashboard.json`; they are not stored in SQLite today.
