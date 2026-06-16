# Database Schema (MVP1)

The project requires storage of historical data, strategy configurations, and backtesting results. Below is a relational schema (SQLite/PostgreSQL) with entities and relationships for the first development phase (MVP1).

## 2.1 Entities and attributes (MVP1)

| Entity            | Attributes (field, type, description)                                                                                  | Relationships                                                          |
|-------------------|------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| **Candle**        | `id` SERIAL PK<br>`instrument` VARCHAR(20) NOT NULL<br>`timeframe` VARCHAR(10) NOT NULL<br>`timestamp` TIMESTAMP NOT NULL<br>`open` DECIMAL(12,4)<br>`high` DECIMAL(12,4)<br>`low` DECIMAL(12,4)<br>`close` DECIMAL(12,4)<br>`volume` BIGINT<br>UNIQUE(instrument, timeframe, timestamp) | (no foreign keys)                                                      |
| **Strategy**      | `id` SERIAL PK<br>`name` VARCHAR(100) UNIQUE NOT NULL<br>`yaml_config` TEXT NOT NULL<br>`created_at` TIMESTAMP DEFAULT NOW() | 1 : N → backtest_runs                                                 |
| **backtest_runs** | `id` SERIAL PK<br>`strategy_id` INT FK → Strategy.id<br>`instrument` VARCHAR(20) NOT NULL<br>`from_dt` TIMESTAMP NOT NULL<br>`to_dt` TIMESTAMP NOT NULL<br>`status` VARCHAR(20) (pending, running, completed, failed) | N : 1 → Strategy<br>1 : N → trades<br>1 : 1 → metrics (optional)      |
| **trades**        | `id` SERIAL PK<br>`run_id` INT FK → backtest_runs.id<br>`entry_price` DECIMAL(12,4)<br>`exit_price` DECIMAL(12,4)<br>`quantity` DECIMAL(18,8)<br>`pnl` DECIMAL(12,4)<br>`opened_at` TIMESTAMP<br>`closed_at` TIMESTAMP | N : 1 → backtest_runs                                                  |
| **metrics**       | `id` SERIAL PK<br>`run_id` INT UNIQUE FK → backtest_runs.id<br>`total_pnl` DECIMAL(12,4)<br>`sharpe_ratio` DECIMAL(8,4)<br>`max_drawdown` DECIMAL(8,4)<br>`win_rate` DECIMAL(5,4)<br>`deposit_baseline_pnl` DECIMAL(12,4) | 1 : 1 → backtest_runs (unique foreign key)                             |

## 2.2 ER diagram (text description)

```text
┌──────────────┐          ┌─────────────────┐
│   Strategy   │          │    Candle       │
│──────────────│          │─────────────────│
│ id (PK)      │◄──────┐  │ id (PK)         │
│ name         │       │  │ instrument      │
│ yaml_config  │       │  │ timeframe       │
│ created_at   │       │  │ timestamp       │
└──────────────┘       │  │ open, high, ... │
         │             │  └─────────────────┘
         │             │
         │ 1           │ (independent entities,
         │             │  linked via instrument
         ▼             │  and dates in backtests)
┌────────────────────┐ │
│   backtest_runs    │ │
│────────────────────│ │
│ id (PK)            │ │
│ strategy_id (FK)   │ │
│ instrument         │ │
│ from_dt, to_dt     │ │
│ status             │ │
└────────────────────┘ │
         │ 1           │
         │             │
         │ 0..*        │
         ▼             │
┌────────────────────┐ │
│      trades        │ │
│────────────────────│ │
│ id (PK)            │ │
│ run_id (FK)        │ │
│ entry_price        │ │
│ exit_price         │ │
│ quantity, pnl      │ │
│ opened_at, closed_at│ │
└────────────────────┘ │
         │             │
         │ 1           │
         │             │
         │ 0..1        │
         ▼             │
┌────────────────────┐ │
│     metrics        │ │
│────────────────────│ │
│ id (PK)            │ │
│ run_id (UNIQUE FK) │ │
│ total_pnl          │ │
│ sharpe_ratio       │ │
│ max_drawdown       │ │
│ win_rate           │ │
│ deposit_baseline_pnl│ │
└────────────────────┘ │
