# Backtesting Design Artifacts

The PDFs in this directory are Week 2 design snapshots dated June 16, 2026:

- `Shared_Simulation_Core.pdf` — Issue #32;
- `Backtest&Validation_Execution.pdf` — Issue #33.

They remain useful target-architecture references, but they are not current implementation
documentation.

As of June 23, 2026:

- `ExecutionEngine.run(strategy, candles, initial_capital)` is implemented;
- candle-by-candle `ExecutionContext` and BUY/SELL/HOLD processing are implemented;
- equity curve, TradeLog, analytics, and final-position close are implemented;
- only one strategy is run at a time;
- validation mode, multi-strategy orchestration, PostgreSQL persistence, Top-N workflow,
  scheduler, and trading bot are not implemented.

For current contracts, see:

- [`../interfaces_description.md`](../interfaces_description.md);
- [`../strategy_module_architecture.md`](../strategy_module_architecture.md);
- [`../analytics_data_model_specification.md`](../analytics_data_model_specification.md);
- [`../../README.md`](../../README.md).
