# Documentation Status

Last audited against `main`: **July 7, 2026** (Week 5 milestone close; PR #137 CI baseline).

Use this page to distinguish current implementation references from target architecture and
historical course artifacts.

## Source of Truth

For current behavior, use this order:

1. application code and tests;
2. current Markdown references listed below;
3. Git history and merged pull requests;
4. target/historical artifacts.

Week 5 engineering merged PRs #105–#107, #127–#128, #130, #134–#136 (July 1–7, 2026) and
PR #137 (GitHub-hosted CI on `ubuntu-latest`). The audit baseline reflects that state.

## Current Implementation References

| Document | Scope |
|---|---|
| [`../README.md`](../README.md) | MVP2 capabilities, quick start, repository layout, limitations |
| [`../DOCKER.md`](../DOCKER.md) | Compose services, CI job matrix, container workflow |
| [`../frontend/README.md`](../frontend/README.md) | MVP2 dashboard routes and frontend workflow |
| [`api_description.md`](api_description.md) | Implemented Next.js routes plus separately labeled target FastAPI API |
| [`interfaces_description.md`](interfaces_description.md) | Engine, strategy, composable, optimization, and broker-facing dataclasses |
| [`strategy_module_architecture.md`](strategy_module_architecture.md) | Strategy contract, plugin strategies, composable engine overview |
| [`strategy_composable_engine_design.md`](strategy_composable_engine_design.md) | **Implemented** composable rule engine (bilingual EN/RU); architecture reference |
| [`broker_adapter_description.md`](broker_adapter_description.md) | T-Bank live path; TwelveData/Bybit example adapters |
| [`core_perfomance_metrics.md`](core_perfomance_metrics.md) | Implemented metric formulas and edge cases |
| [`analytics_data_model_specification.md`](analytics_data_model_specification.md) | In-memory analytics, ranking, validation metrics; target persistence |
| [`database_schema.md`](database_schema.md) | Implemented SQLite candle storage plus target relational run schema |

## Implemented vs Planned (Week 5)

| Area | Status |
|---|---|
| Composable YAML strategies (`config/strategies/*.yaml`) | Implemented |
| Trigger/action rules with TP/SL and priority ordering | Implemented |
| Parameter optimizer (grid + random sample) | Implemented |
| MVP2 dashboard with Run/Stop, optimization panel | Implemented |
| Instrument dropdown (19 MOEX tickers, single-instrument) | Partial |
| GitHub Actions CI (`backend-tests`, `frontend-checks`, `docker-smoke` on `ubuntu-latest`) | Implemented |
| Plugin strategies (`ma_crossover`, `ma_rsi`, `rsi_threshold`) | Implemented (codebase; dashboard uses composable YAML) |
| Data Loader single-fetch reuse for optimizer | Implemented |
| In-memory Top-N ranking and validation metrics library | Implemented |
| TwelveData / Bybit example adapters | Implemented (examples only; dashboard uses T-Bank) |
| Multi-period stability validation | Planned (Week 6 customer priority) |
| End-to-end validation workflow (holdout second stage) | Not integrated |
| FastAPI service (`src/api`) | Planned |
| Relational run/trade/metrics persistence | Planned |
| Multi-instrument portfolio UI | Planned |
| CSV adapter, order placement, scheduler, notifications, trading bot | Planned |

## Target Architecture / Historical Design

These files describe target or proposed architecture. They are not a complete description
of the current MVP unless marked as implemented:

- [`strategy_composable_engine_design.md`](strategy_composable_engine_design.md) — implemented
  declarative rule engine (July 2026; bilingual EN/RU); kept as architecture reference.

Historical Week 2 design records:

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
- only the T-Bank candle-read path is wired into `main.py` for live fetches;
- composable YAML strategies run end to end with optimization in the dashboard;
- CI uses GitHub-hosted `ubuntu-latest` runners (replaced self-hosted PR smoke in PR #137).

## Historical Reports

Files under `reports/` are dated course submissions. Week 1 and Week 2 reports intentionally
retain statements that were true at submission time. They must not be edited to reflect later
implementation.

The Week 5 Markdown report is the latest course status snapshot:

- [`../reports/Week 5 report.md`](../reports/Week%205%20report.md)
- [`../reports/Week 5 report.pdf`](../reports/Week%205%20report.pdf)

Earlier reports remain historical:

- [`../reports/Week 4 report.md`](../reports/Week%204%20report.md)
- [`../reports/Week 3 report.md`](../reports/Week%203%20report.md)

## Audit Checklist

When behavior changes, update:

- root and relevant module README;
- implemented route documentation;
- model/strategy contracts;
- Docker service/command documentation and CI job table in `DOCKER.md`;
- current limitations and test count;
- current lint/build warnings and failures;
- this status matrix when a placeholder becomes implemented.
