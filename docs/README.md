# Documentation Status

Last audited against `main`: **July 20, 2026**.

Use this page to distinguish current implementation references from target architecture and
historical course artifacts.

## Source of Truth

For current behavior, use this order:

1. application code and tests;
2. current Markdown references listed below;
3. Git history and merged pull requests;
4. target/historical artifacts.

Living docs on this page reflect current HEAD (bootstrap, chunked candle fetch, Live refresh,
Strategy health verdict). Explore dock, trading bot dock, and `src/stability.py` were removed
from the dashboard in July 2026.

## Current Implementation References

| Document | Scope |
|---|---|
| [`README.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/README.md) | Product overview, quick start, architecture, API, limitations |
| [`DOCKER.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/DOCKER.md) | Compose services, `.env` security, CI job matrix, container workflow |
| [`frontend/README.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/frontend/README.md) | Dashboard UI: bootstrap, Live refresh, run progress, tokens |
| [`api_description.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/api_description.md) | Implemented Next.js routes plus separately labeled target FastAPI API |
| [`openapi.yaml`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/openapi.yaml) | OpenAPI 3 spec; interactive Swagger UI at `/docs` when frontend runs |
| [`interfaces_description.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/interfaces_description.md) | Engine, strategy, composable, optimization, live-run, broker dataclasses |
| [`strategy_module_architecture.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/strategy_module_architecture.md) | Strategy contract, plugin strategies, composable engine overview |
| [`strategy_composable_engine_design.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/strategy_composable_engine_design.md) | **Implemented** composable rule engine (bilingual EN/RU); architecture reference |
| [`broker_adapter_description.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/broker_adapter_description.md) | Factory sources: T-Bank, TwelveData, Bybit, Binance |
| [`core_perfomance_metrics.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/core_perfomance_metrics.md) | Implemented metric formulas and edge cases |
| [`analytics_data_model_specification.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/analytics_data_model_specification.md) | In-memory analytics, Top-N, optimizer `ranked[]`, strategy health verdict |
| [`database_schema.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/database_schema.md) | Implemented SQLite candle storage plus target relational run schema |

## Implemented vs Planned

| Area | Status |
|---|---|
| Composable YAML strategies (`config/strategies/*.yaml`) | Implemented |
| Trigger/action rules with TP/SL and priority ordering | Implemented |
| Constraints, time filters, trailing stop, drawdown/trend guards (#142) | Implemented |
| Parameter optimizer (grid + random sample) | Implemented |
| Optimizer parameter ranking (`ranked[]`, PR #139) | Implemented |
| Strategy Top-N ranking (`build_top_n`) | Implemented |
| Dashboard with Run/Stop, optimization panel, Live refresh (one strategy) | Implemented |
| Bootstrap progress bar (`GET /api/run-progress`, chunked fetch + backtest phases) | Implemented |
| Strategy health verdict (PASS / CAUTION / FAIL) | Implemented |
| Per-strategy `enabled` flag for next bootstrap (`PATCH /api/strategies/{id}`) | Implemented |
| Chunked candle loading + SQLite cache (`src/data_loader/backtest_fetch.py`) | Implemented |
| Multi-API data sources (T-Bank, Twelve Data, Bybit, Binance) + token UI | Implemented |
| Instrument dropdown (single-instrument) | Partial |
| Commission / slippage in execution engine | Implemented |
| GitHub Actions CI (`backend-tests`, `frontend-checks`, `docker-smoke` on `ubuntu-latest`) | Implemented |
| Plugin strategies (`ma_crossover`, `ma_rsi`, `rsi_threshold`) | Implemented (codebase; dashboard uses composable YAML) |
| Explore dock + `/api/explore` | **Removed** |
| Trading bot dock + `/api/bot` | **Removed** |
| `src/stability.py` window explore analytics | **Removed** |
| Full multi-period / walk-forward stability ranking | Planned |
| End-to-end holdout validation workflow (second stage) | Not integrated |
| FastAPI service (`src/api`) | Planned |
| Relational run/trade/metrics persistence | Planned |
| Multi-instrument portfolio UI | Planned |
| CSV adapter, T-Bank `place_order` / `get_portfolio`, scheduler, notifications, live order automation | Planned / stubs |

## Target Architecture / Historical Design

These files describe target or proposed architecture. They are not a complete description
of the current MVP unless marked as implemented:

- [`strategy_composable_engine_design.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/strategy_composable_engine_design.md) — implemented
  declarative rule engine (July 2026; bilingual EN/RU); kept as architecture reference;
  constraints/trailing surfaces from PR #142 are implemented in code.

Historical Week 2 design records:

- [`Product description.docx`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/Product%20description.docx) — product vision and target
  static/dynamic/deployment architecture;
- [`Backtesting/Shared_Simulation_Core.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/Backtesting/Shared_Simulation_Core.pdf) —
  Issue #32 design snapshot dated June 16;
- [`Backtesting/Backtest&Validation_Execution.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/Backtesting/Backtest%26Validation_Execution.pdf)
  — Issue #33 design snapshot dated June 16.

Important differences from early target docs:

- there is no operational FastAPI service;
- relational run history, trades, and metrics tables are not implemented;
- the integrated app is one full-stack container plus JSON runtime state and SQLite
  candle cache;
- dashboard and Live refresh select brokers through the adapter factory (not T-Bank-only);
- composable YAML strategies run end to end with optimization and ranking;
- CI uses GitHub-hosted `ubuntu-latest` runners (PR #137).

## Historical Reports

Files under `reports/` are dated course submissions. Week 1 and Week 2 reports intentionally
retain statements that were true at submission time. They must not be edited to reflect later
implementation.

The **Final Report** synthesizes the full course for submission (frozen commit URL inside):

- [`Final report.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20report.md)
- [`Final report.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20report.pdf) (after PDF export)

The **Final Presentation** slide deck supports the course final video (~5 min + ~2 min demo):

- [`Final presentation.md`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20presentation.md)
- [`Final presentation.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20presentation.pdf)

The Week 6 report is the latest formal course weekly snapshot (July 14). Living docs
above remain the day-to-day source of truth for HEAD; weekly reports are dated submissions:

- [`Week 6 report.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%206%20report.pdf)
- [`Week 5 report.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%205%20report.pdf)

Earlier reports remain historical:

- [`Week 4 report.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%204%20report.pdf)
- [`Week 3 report.pdf`](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%203%20report.pdf)

## Audit Checklist

When behavior changes, update:

- root and relevant module README;
- implemented route documentation;
- model/strategy contracts;
- Docker service/command documentation and CI job table in `DOCKER.md`;
- current limitations and test count;
- current lint/build warnings and failures;
- this status matrix when a placeholder becomes implemented.
