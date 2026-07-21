# Backtesting Design Artifacts

The PDFs in this directory are Week 2 design snapshots dated June 16, 2026:

- `Shared_Simulation_Core.pdf` — Issue #32;
- `Backtest&Validation_Execution.pdf` — Issue #33.

They remain useful target-architecture references, but they are not current implementation
documentation.

As of July 19, 2026:

- `ExecutionEngine.run(strategy, candles, initial_capital)` is implemented;
- candle-by-candle `ExecutionContext` and BUY/SELL/HOLD processing are implemented;
- equity curve, TradeLog, analytics, and final-position close are implemented;
- dashboard runs multiple strategies in one bootstrap; Live refresh reruns one strategy;
- validation mode, PostgreSQL persistence, scheduler, and live order routing are not implemented.

For current contracts, see:

- [`interfaces_description.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/interfaces_description.md);
- [`strategy_module_architecture.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/strategy_module_architecture.md);
- [`analytics_data_model_specification.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/analytics_data_model_specification.md);
- [`README.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/README.md).
