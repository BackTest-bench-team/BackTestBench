"""Demo: run the ma_crossover strategy through the ExecutionEngine.

Run from the repo root with the src root on the path, e.g.:

    PYTHONPATH=src python examples/run_ma_crossover_demo.py
"""

from __future__ import annotations

import math

from src.engine import ExecutionEngine
from src.engine.models import Candle

from src.strategy import load_config, create_from_config, available_strategies


def synthetic_candles(n: int = 200) -> list[Candle]:
    out = []
    for i in range(n):
        p = 100.0 + 12.0 * math.sin(i / 7.0)
        out.append(Candle(timestamp=str(i), open=p, high=p + 1, low=p - 1, close=p, volume=1000.0))
    return out


def main() -> None:
    print("registered strategies:", available_strategies())

    cfg = load_config("config/strategies/ma_crossover.yaml")
    print(f"loaded config: {cfg.name}  params={cfg.params}")

    strategy = create_from_config(cfg)
    result = ExecutionEngine().run(strategy, synthetic_candles(), initial_capital=10_000.0)

    trades = result["trade_log"]
    portfolio = result["final_portfolio"]
    print(f"completed trades: {len(trades)}")
    print(f"final equity: {portfolio.equity:.2f}")
    if trades:
        t = trades[0]
        print(f"first trade: entry={t.entry_price:.2f} exit={t.exit_price:.2f} pnl={t.pnl:.2f}")


if __name__ == "__main__":
    main()
