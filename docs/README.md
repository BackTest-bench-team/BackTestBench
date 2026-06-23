# Documentation Status

Last audited against `main`: **June 23, 2026**.

Use this page to distinguish current implementation references from target architecture and
historical course artifacts.

## Source of Truth

For current behavior, use this order:

1. application code and tests;
2. current Markdown references listed below;
3. Git history and merged pull requests;
4. target/historical artifacts.

No commits were added to `main` after June 22 during the June 18–23 audit window.

## Current Implementation References

| Document | Scope |
|---|---|
| [`../README.md`](../README.md) | MVP capabilities, quick start, repository layout, limitations |
| [`../DOCKER.md`](../DOCKER.md) | Current Compose services and container workflow |
| [`../frontend/README.md`](../frontend/README.md) | Current dashboard routes and frontend workflow |
| [`api_description.md`](api_description.md) | Implemented Next.js routes plus separately labeled target FastAPI API |
| [`interfaces_description.md`](interfaces_description.md) | Current engine, strategy, analytics, and broker-facing dataclasses |
| [`strategy_module_architecture.md`](strategy_module_architecture.md) | Current strategy contract and MA Crossover behavior |
| [`broker_adapter_description.md`](broker_adapter_description.md) | Current T-Bank read path and unimplemented broker operations |
| [`core_perfomance_metrics.md`](core_perfomance_metrics.md) | Implemented metric formulas and edge cases |
| [`analytics_data_model_specification.md`](analytics_data_model_specification.md) | Current in-memory analytics models and target persistence |
| [`database_schema.md`](database_schema.md) | Target relational schema; explicitly not implemented |

## Target Architecture / Historical Design

These files were produced during Week 2 and remain useful design records. They are not a
complete description of the Week 3 implementation:

- [`Product description.docx`](Product%20description.docx) — product vision and target
  static/dynamic/deployment architecture;
- [`Backtesting/Shared_Simulation_Core.pdf`](Backtesting/Shared_Simulation_Core.pdf) —
  Issue #32 design snapshot dated June 16;
- [`Backtesting/Backtest&Validation_Execution.pdf`](Backtesting/Backtest&Validation_Execution.pdf)
  — Issue #33 design snapshot dated June 16.

Important differences from the current MVP:

- there is no operational FastAPI service or relational database;
- Data Loader, DB, API, CSV adapter, scheduler, notifications, and trading bot modules are
  placeholders or future work;
- the integrated app is one full-stack container plus a JSON runtime-state file;
- only the T-Bank candle-read path is implemented;
- only one strategy and one predefined dashboard run are wired end to end.

## Historical Reports

Files under `reports/` are dated course submissions. Week 1 and Week 2 reports intentionally
retain statements that were true at submission time. They must not be edited to reflect later
implementation.

The Week 3 Markdown report is the latest course status snapshot:

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
