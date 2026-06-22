import asyncio
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.analytics import calculate_metrics_from_trade_log
from src.broker_adapter import TBankAdapter
from src.engine import ExecutionEngine, RunContext
from src.strategy.strategies.ma_crossover import MACrossover

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DASHBOARD_FILE = DATA_DIR / "runtime-dashboard.json"

load_dotenv(BASE_DIR / ".env", override=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def default_dashboard() -> Dict[str, Any]:
    return {
        "run_id": "local",
        "strategy_id": "ma_crossover",
        "strategy_version": "1",
        "instrument": "SBER",
        "timeframe": "1h",
        "data_source": "T-Bank",
        "status": "idle",
        "current_stage": "Idle",
        "pipeline": [
            {"name": "Broker Adapter", "status": "pending"},
            {"name": "Strategy Module", "status": "pending"},
            {"name": "Simulation Engine", "status": "pending"},
            {"name": "Analytics Module", "status": "pending"},
        ],
        "metrics": {
            "total_pnl": None,
            "sharpe_ratio": None,
            "max_drawdown": None,
            "win_rate": None,
            "deposit_baseline_pnl": None,
        },
        "equity_points": [],
        "trade_count": 0,
        "final_portfolio": {
            "cash": None,
            "position_size": None,
            "equity": None,
        },
        "message": "No completed run yet",
        "error": None,
        "last_updated": None,
    }


def load_dashboard() -> Dict[str, Any]:
    if not DASHBOARD_FILE.exists():
        return default_dashboard()

    try:
        with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_dashboard()
    except Exception:
        return default_dashboard()

    merged = default_dashboard()
    merged.update({k: v for k, v in data.items() if k not in {"metrics", "final_portfolio"}})

    metrics = deepcopy(merged["metrics"])
    if isinstance(data.get("metrics"), dict):
        metrics.update(data["metrics"])
    merged["metrics"] = metrics

    final_portfolio = deepcopy(merged["final_portfolio"])
    if isinstance(data.get("final_portfolio"), dict):
        final_portfolio.update(data["final_portfolio"])
    merged["final_portfolio"] = final_portfolio

    if isinstance(data.get("pipeline"), list):
        merged["pipeline"] = data["pipeline"]

    if isinstance(data.get("equity_points"), list):
        merged["equity_points"] = data["equity_points"]

    return merged


def save_dashboard(data: Dict[str, Any]) -> None:
    current = load_dashboard()
    merged = deepcopy(current)

    for key, value in data.items():
        if key == "metrics" and isinstance(value, dict):
            merged["metrics"].update(value)
        elif key == "final_portfolio" and isinstance(value, dict):
            merged["final_portfolio"].update(value)
        else:
            merged[key] = value

    merged["last_updated"] = now_iso()

    tmp_path = DASHBOARD_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)
    os.replace(tmp_path, DASHBOARD_FILE)


def set_step_status(dashboard: Dict[str, Any], step_name: str, status: str) -> None:
    for step in dashboard["pipeline"]:
        if step["name"] == step_name:
            step["status"] = status
            return


def build_equity_points(equity_curve):
    points = []
    for i, value in enumerate(equity_curve):
        points.append(
            {
                "date": str(i),
                "value": float(value),
            }
        )
    return points


async def run_pipeline() -> Dict[str, Any]:
    run_id = os.getenv("RUN_ID") or make_run_id()

    dashboard = default_dashboard()
    dashboard["run_id"] = run_id
    dashboard["status"] = "running"
    dashboard["current_stage"] = "Broker Adapter"
    dashboard["message"] = "Starting pipeline..."
    dashboard["error"] = None
    set_step_status(dashboard, "Broker Adapter", "running")
    save_dashboard(dashboard)

    token = os.getenv("TINKOFF_TOKEN")
    if not token:
        raise RuntimeError("TINKOFF_TOKEN missing")

    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=30)

    adapter = TBankAdapter(
        token=token,
        use_sandbox=False,
        verify_ssl=False,
    )

    async with adapter:
        candles = await adapter.get_candles(
            instrument="SBER",
            timeframe="1h",
            from_dt=from_dt,
            to_dt=to_dt,
        )

    if not candles:
        raise RuntimeError("Broker returned 0 candles")

    dashboard["current_stage"] = "Strategy Module"
    dashboard["message"] = "Creating strategy..."
    set_step_status(dashboard, "Broker Adapter", "done")
    set_step_status(dashboard, "Strategy Module", "running")
    save_dashboard(dashboard)

    strategy = MACrossover(
        params={
            "fast": 15,
            "slow": 20,
            "order_size": 1.0,
        }
    )

    dashboard["current_stage"] = "Simulation Engine"
    dashboard["message"] = "Running backtest..."
    set_step_status(dashboard, "Strategy Module", "done")
    set_step_status(dashboard, "Simulation Engine", "running")
    save_dashboard(dashboard)

    engine = ExecutionEngine()
    result = engine.run(
        strategy=strategy,
        candles=candles,
        initial_capital=100000.0,
    )

    trade_log = result["trade_log_report"]
    equity_curve = result["equity_curve"]
    final_portfolio = result["final_portfolio"]

    dashboard["trade_count"] = len(trade_log.trades)
    dashboard["equity_points"] = build_equity_points(equity_curve)
    dashboard["final_portfolio"] = {
        "cash": float(final_portfolio.cash),
        "position_size": float(final_portfolio.position_size),
        "equity": float(final_portfolio.equity),
    }
    dashboard["current_stage"] = "Analytics Module"
    dashboard["message"] = "Calculating metrics..."
    set_step_status(dashboard, "Simulation Engine", "done")
    set_step_status(dashboard, "Analytics Module", "running")
    save_dashboard(dashboard)

    context = RunContext(
        run_id=run_id,
        strategy_id="ma_crossover",
        strategy_version="1",
        instrument="SBER",
        timeframe="1h",
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=100000.0,
    )

    metrics = calculate_metrics_from_trade_log(trade_log, context)

    dashboard["metrics"] = {
        "total_pnl": float(metrics.total_pnl),
        "sharpe_ratio": float(metrics.sharpe_ratio),
        "max_drawdown": float(metrics.max_drawdown),
        "win_rate": float(metrics.win_rate),
        "deposit_baseline_pnl": float(metrics.deposit_baseline_pnl),
    }
    dashboard["status"] = "completed"
    dashboard["current_stage"] = "Finished"
    dashboard["message"] = "Backtest completed successfully"
    dashboard["error"] = None
    set_step_status(dashboard, "Analytics Module", "done")

    save_dashboard(dashboard)
    return dashboard


if __name__ == "__main__":
    try:
        result = asyncio.run(run_pipeline())
        print(result)
    except Exception as e:
        failed = load_dashboard()
        failed["status"] = "error"
        failed["current_stage"] = "Failed"
        failed["message"] = "Pipeline failed"
        failed["error"] = str(e)
        if isinstance(failed.get("pipeline"), list):
            for step in failed["pipeline"]:
                if step["status"] == "running":
                    step["status"] = "error"
        save_dashboard(failed)
        print("PIPELINE FAILED:", e)