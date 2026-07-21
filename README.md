# BackTestBench

Platform for backtesting long-only trading strategies on historical market data. Load candles
from T-Bank, Twelve Data, Bybit, or Binance, run and compare YAML-based strategies, optimize
parameters, and review metrics and charts in a web dashboard.

## What you can do

- Run backtests on historical OHLCV candles with commission and slippage settings.
- Connect market data providers and save API tokens from the dashboard.
- Manage strategies: enable/disable, add new YAML strategies, compare ranking and health
  verdicts (PASS / CAUTION / FAIL).
- Optimize strategy parameters (grid or random sample) and inspect top candidates.
- View equity curves, trade logs, buy/sell markers, and buy-and-hold benchmark on charts.
- Refresh one strategy in **Live** mode on an interval while a full backtest is not running.
- Start the full stack with Docker Compose or run frontend + Python locally for development.

## Get started

**1. Configure tokens**

```bash
cp .env.example .env
```

Set at least `TINKOFF_TOKEN` for MOEX data via T-Bank. Optional: `TWELVEDATA_TOKEN`,
`BYBIT_TOKEN`, `BINANCE_TOKEN`. Tokens can also be entered in the dashboard UI.

**2. Start with Docker**

```bash
docker compose up --build
```

Open <http://localhost> (or the port from `APP_PORT`, default 80).

**Course VM (always-on demo):** <http://10.93.27.6/> — same Docker Compose stack as above, deployed for TA access.

**3. Run a backtest**

1. Choose a data source and instrument in the control panel.
2. Mark strategies you want to run ( **Run** checkbox on each card ).
3. Click **Run backtest** and wait for the progress bar to finish.
4. Review metrics, ranking, and charts on strategy cards.

Interactive API reference: <http://localhost/docs>.

Stop the stack:

```bash
docker compose down
```

More Docker options (backend-only, tests, dev shell): [DOCKER.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/DOCKER.md).

## Dashboard guide

| Action | Where |
|---|---|
| Data source & instrument | Backtest control panel |
| API tokens | Data source cards or root `.env` |
| Run / stop full backtest | **Run backtest** / **Stop backtest** |
| Include strategy in next run | **Run** checkbox on strategy card |
| Live refresh (one strategy) | **Go Live** / **Stop Live** on a card |
| Add strategy | Add Strategy panel (writes YAML to `config/strategies/`) |
| Optimization mode | Control panel — grid or random sample |

Settings are stored in `config/dashboard.json`. Strategy definitions live in
`config/strategies/*.yaml`.

## Local development

**Requirements:** Python 3.10+, Node.js 20+, npm. Docker optional but recommended.

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
npm --prefix frontend ci && npm --prefix frontend run dev
```

Open the URL printed by the dev server. Backend CLI:

```bash
python main.py bootstrap
python main.py refresh-ranking
```

**Verification:** `pytest tests -q && npm --prefix frontend run lint && npm --prefix frontend run build`

## Documentation

| Document | Description |
|---|---|
| [docs/README.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/README.md) | Documentation hub |
| [DOCKER.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/DOCKER.md) | Docker services and deployment |
| [frontend/README.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/frontend/README.md) | Dashboard UI details |
| [docs/openapi.yaml](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/openapi.yaml) | OpenAPI spec (Swagger at `/docs`) |
| [docs/api_description.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/api_description.md) | HTTP route reference |
| [docs/strategy_composable_engine_design.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/strategy_composable_engine_design.md) | Strategy YAML format |
| [docs/analytics_data_model_specification.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/docs/analytics_data_model_specification.md) | Metrics and ranking |

## Reports

- [Final Report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20report.pdf)
- [Final Presentation (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Final%20presentation.pdf)
- [Week 2 report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%202%20report.pdf)
- [Week 6 report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%206%20report.pdf)
- [Week 5 report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%205%20report.pdf)
- [Week 4 report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%204%20report.pdf)
- [Week 3 report (PDF)](https://github.com/BackTest-bench-team/BackTestBench/blob/main/reports/Week%203%20report.pdf)

## Disclaimer

BackTestBench uses historical market data for research. It does **not** place real trades.
Results are not financial advice and do not guarantee future performance. Keep `.env` and API
tokens private; see [DOCKER.md](https://github.com/BackTest-bench-team/BackTestBench/blob/main/DOCKER.md) for server deployment notes.
