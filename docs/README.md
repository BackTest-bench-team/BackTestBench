# Documentation Status

Last audited against `main`: **June 30, 2026** (Week 4 milestone close).

Use this page to distinguish current implementation references from target architecture and
historical course artifacts.

## Source of Truth

For current behavior, use this order:

1. application code and tests;
2. current Markdown references listed below;
3. Git history and merged pull requests;
4. target/historical artifacts.

Week 4 engineering merged PRs #98–#102 (June 24–30, 2026). The audit baseline reflects that
state.

## Current Implementation References

| Document | Scope |
|---|---|
| [`../README.md`](../README.md) | MVP capabilities, quick start, repository layout, limitations |
| [`../DOCKER.md`](../DOCKER.md) | Current Compose services and container workflow |
| [`../frontend/README.md`](../frontend/README.md) | Current dashboard routes and frontend workflow |
| [`api_description.md`](api_description.md) | Implemented Next.js routes plus separately labeled target FastAPI API |
| [`interfaces_description.md`](interfaces_description.md) | Engine, strategy, analytics, data loader, broker, and dashboard contracts |
| [`strategy_module_architecture.md`](strategy_module_architecture.md) | Strategy contract, plugin loading, built-in strategies, ParameterSpec |
| [`strategy_module_plugins_and_configuration.md`](strategy_module_plugins_and_configuration.md) | Plugin discovery, YAML configs, dashboard parameter schemas |
| [`broker_adapter_description.md`](broker_adapter_description.md) | Current T-Bank read path and unimplemented broker operations |
| [`core_perfomance_metrics.md`](core_perfomance_metrics.md) | Implemented metric formulas and edge cases |
| [`analytics_data_model_specification.md`](analytics_data_model_specification.md) | In-memory analytics, ranking, validation metrics; target persistence |
| [`database_schema.md`](database_schema.md) | Implemented SQLite candle storage plus target relational run schema |

## Implemented vs Planned (Week 4)

| Area | Status |
|---|---|
| Three built-in strategies (`ma_crossover`, `ma_rsi`, `rsi_threshold`) | Implemented |
| Plugin auto-discovery and YAML configs | Implemented |
| `ParameterSpec` / dashboard parameter editors | Implemented |
| Multi-strategy dashboard, ranking panel, benchmark chart | Implemented |
| Data Loader validation, SQLite candle upsert, cache reuse | Implemented |
| Configurable instrument/timeframe/lookback via `config/dashboard.json` | Implemented (UI picker deferred) |
| In-memory Top-N ranking and validation metrics | Implemented |
| FastAPI service (`src/api`) | Planned |
| Relational run/trade/metrics persistence | Planned |
| Multi-instrument UI picker | Deferred to Week 5 |
| TP/SL, trigger/action abstraction, parameter optimizer | Deferred to Week 5 |
| Explicit Calculate/Run submit UX | Deferred to Week 5 |
| CSV adapter, order placement, scheduler, notifications, trading bot | Planned |

## Target Architecture / Historical Design

These files were produced during Week 2 and remain useful design records. They are not a
complete description of the Week 4 implementation:

- [`Product description.docx`](Product%20description.docx) — product vision and target
  static/dynamic/deployment architecture;
- [`Backtesting/Shared_Simulation_Core.pdf`](Backtesting/Shared_Simulation_Core.pdf) —
  Issue #32 design snapshot dated June 16;
- [`Backtesting/Backtest&Validation_Execution.pdf`](Backtesting/Backtest&Validation_Execution.pdf)
  — Issue #33 design snapshot dated June 16.

Important differences from the current MVP:

- there is no operational FastAPI service;
- relational run history, trades, and metrics tables are not implemented;
- the integrated app is one full-stack container plus JSON runtime state and SQLite candle cache;
- only the T-Bank candle-read path is implemented for live fetches;
- three strategies run end to end with configurable parameters in the dashboard.

## Historical Reports

Files under `reports/` are dated course submissions. Week 1 and Week 2 reports intentionally
retain statements that were true at submission time. They must not be edited to reflect later
implementation.

The Week 4 Markdown report is the latest course status snapshot:

- [`../reports/Week 4 report.md`](../reports/Week%204%20report.md)

Earlier reports remain historical:

- [`../reports/Week 3 report.md`](../reports/Week%203%20report.md)

## Audit Checklist

When behavior changes, update:

- root and relevant module README;
- implemented route documentation;
- model/strategy contracts;
- Docker service/command documentation;
- current limitations and test count;
- current lint/build warnings and failures;
- this status matrix when a placeholder becomes implemented.
