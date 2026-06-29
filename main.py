import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import src.strategy.strategies  # noqa: F401 — register built-in strategies

from src.analytics import RankingConfig, TopNEntry, build_top_n, calculate_metrics_from_trade_log
from src.engine.models import MetricsReport
from src.broker_adapter import TBankAdapter
from src.data_loader import DataLoader, candle_model_to_engine
from src.data_loader.loader import utc_naive
from src.db import init_db
from src.engine import ExecutionEngine, RunContext
from src.engine.models import Candle, Trade
from src.strategy import create_strategy, describe_strategy
from src.strategy.schema import ORDER_SIZE_MAX

DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config" / "dashboard.json"
DASHBOARD_FILE = DATA_DIR / "runtime-dashboard.json"

DATA_DIR.mkdir(exist_ok=True)
load_dotenv(BASE_DIR / ".env", override=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict[str, Any]:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def normalize_order_size(params: dict[str, Any]) -> dict[str, Any]:
    """Clamp order_size into the allowed range (1 … ORDER_SIZE_MAX)."""
    if "order_size" not in params:
        return params
    out = dict(params)
    size = float(out["order_size"])
    if size > ORDER_SIZE_MAX or size < 1:
        out["order_size"] = 1.0
    return out


def sanitize_config() -> None:
    """Fix saved strategy params in config/dashboard.json."""
    config = load_config()
    changed = False
    for item in config.get("strategies", []):
        fixed = normalize_order_size(item.get("params", {}))
        if fixed != item.get("params"):
            item["params"] = fixed
            changed = True
    if changed:
        save_config(config)


def repair_runtime_dashboard() -> None:
    """Unstick dashboard entries left in running state with invalid order_size."""
    if not DASHBOARD_FILE.exists():
        return
    dashboard = load_dashboard()
    changed = False
    for entry in dashboard.get("strategies", []):
        raw_params = entry.get("params") or {}
        had_bad_size = float(raw_params.get("order_size", 1)) > ORDER_SIZE_MAX
        fixed = normalize_order_size(raw_params)
        if fixed != raw_params:
            entry["params"] = fixed
            changed = True
        if had_bad_size and entry.get("status") == "running":
            entry["status"] = "error"
            entry["error"] = f"order_size must be <= {ORDER_SIZE_MAX}; value reset to 1."
            changed = True
    if changed:
        save_dashboard(dashboard)


def update_config_params(strategy_id: str, params: dict[str, Any]) -> None:
    params = normalize_order_size(params)
    config = load_config()
    for item in config["strategies"]:
        if item["id"] == strategy_id:
            item["params"] = params
            break
    save_config(config)


def load_dashboard() -> dict[str, Any]:
    if not DASHBOARD_FILE.exists():
        return default_dashboard()
    try:
        with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default_dashboard()
        if "ranking" not in data:
            data["ranking"] = empty_ranking()
        if not data["ranking"].get("entries") and any(
            entry.get("status") == "completed" for entry in data.get("strategies", [])
        ):
            update_dashboard_ranking(data)
            save_dashboard(data)
        return data
    except Exception:
        return default_dashboard()


def save_dashboard(data: dict[str, Any]) -> None:
    data["last_updated"] = now_iso()
    tmp = DASHBOARD_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, DASHBOARD_FILE)


def empty_metrics() -> dict[str, None]:
    return {
        "total_pnl": None,
        "sharpe_ratio": None,
        "max_drawdown": None,
        "win_rate": None,
        "deposit_baseline_pnl": None,
        "deposit_baseline_final": None,
    }


def empty_portfolio() -> dict[str, None]:
    return {"cash": None, "position_size": None, "equity": None}


def strategy_skeleton(strategy_id: str, params: dict[str, Any], status: str = "running") -> dict[str, Any]:
    meta = describe_strategy(strategy_id)
    return {
        "strategy_id": strategy_id,
        "strategy_version": "1",
        "title": meta.get("title", strategy_id),
        "status": status,
        "params": params,
        "parameter_specs": meta.get("parameters", []),
        "initial_capital": load_config().get("initial_capital", 100_000.0),
        "metrics": empty_metrics(),
        "chart_points": [],
        "trade_log": [],
        "final_portfolio": empty_portfolio(),
        "error": None,
    }


def empty_ranking() -> dict[str, Any]:
    return {"computed_at": None, "entries": []}


def default_dashboard() -> dict[str, Any]:
    config = load_config()
    return {
        "instrument": config.get("instrument", "SBER"),
        "timeframe": config.get("timeframe", "1h"),
        "data_source": "T-Bank",
        "initial_capital": config.get("initial_capital", 100_000.0),
        "strategies": [
            strategy_skeleton(item["id"], dict(item["params"]), status="idle")
            for item in config.get("strategies", [])
        ],
        "ranking": empty_ranking(),
        "last_updated": None,
    }


def find_strategy_entry(dashboard: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    for entry in dashboard.get("strategies", []):
        if entry.get("strategy_id") == strategy_id:
            return entry
    return None


def get_candle_date_range(config: dict[str, Any]) -> tuple[datetime, datetime]:
    to_dt = datetime.now(timezone.utc)
    from_dt = to_dt - timedelta(days=int(config.get("lookback_days", 30)))
    return from_dt, to_dt


def timeframe_to_timedelta(timeframe: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
        "1d": timedelta(days=1),
    }
    return mapping.get(timeframe, timedelta(hours=1))


def db_candles_usable(rows: list, from_dt: datetime, to_dt: datetime, timeframe: str) -> bool:
    """True when DB already has enough candles for this lookback window."""
    if len(rows) < 10:
        return False
    span_seconds = (utc_naive(to_dt) - utc_naive(from_dt)).total_seconds()
    bar_seconds = timeframe_to_timedelta(timeframe).total_seconds()
    expected = max(span_seconds / bar_seconds, 1)
    return len(rows) >= expected * 0.5


async def fetch_candles_from_api(
    config: dict[str, Any],
    from_dt: datetime,
    to_dt: datetime,
) -> list[Candle]:
    token = os.getenv("TINKOFF_TOKEN")
    if not token:
        raise RuntimeError("TINKOFF_TOKEN missing")

    adapter = TBankAdapter(token=token, use_sandbox=False, verify_ssl=False)
    async with adapter:
        candles = await adapter.get_candles(
            instrument=config["instrument"],
            timeframe=config["timeframe"],
            from_dt=from_dt,
            to_dt=to_dt,
        )

    if not candles:
        raise RuntimeError("No candles returned from broker")

    return candles


async def get_candles(config: dict[str, Any]) -> tuple[list[Candle], str]:
    """Load candles: read from DB when fresh, otherwise fetch from T-Bank and store."""
    init_db()
    from_dt, to_dt = get_candle_date_range(config)
    instrument = config["instrument"]
    timeframe = config["timeframe"]

    loader = DataLoader(use_cache=True)
    try:
        rows = loader.load_candles(instrument, timeframe, from_dt, to_dt)
        if db_candles_usable(rows, from_dt, to_dt, timeframe):
            return [candle_model_to_engine(row) for row in rows], "database"

        api_candles = await fetch_candles_from_api(config, from_dt, to_dt)
        loader.store_candles(instrument, timeframe, api_candles)
        rows = loader.load_candles(instrument, timeframe, from_dt, to_dt)
        return [candle_model_to_engine(row) for row in rows] if rows else api_candles, "T-Bank"
    finally:
        loader.close()


def build_chart_series(
    candles: list[Candle],
    equity_curve: list[float],
    initial_capital: float,
) -> list[dict[str, Any]]:
    if not candles or len(equity_curve) < 2:
        return []

    first_close = float(candles[0].close)
    if first_close <= 0:
        return []

    buy_hold_shares = initial_capital / first_close
    points: list[dict[str, Any]] = []

    for i, candle in enumerate(candles):
        equity_idx = i + 1
        if equity_idx >= len(equity_curve):
            break
        close = float(candle.close)
        equity = float(equity_curve[equity_idx])
        benchmark_equity = buy_hold_shares * close
        points.append(
            {
                "date": candle.timestamp,
                "strategy_index": equity / initial_capital * 100.0,
                "benchmark_index": benchmark_equity / initial_capital * 100.0,
                "equity": equity,
                "close": close,
            }
        )
    return points


def build_trade_log(trades: list[Trade]) -> list[dict[str, Any]]:
    log: list[dict[str, Any]] = []
    for trade in trades:
        if trade.opened_at:
            log.append(
                {
                    "timestamp": trade.opened_at,
                    "action": "BUY",
                    "price": float(trade.entry_price),
                }
            )
        if trade.closed_at:
            log.append(
                {
                    "timestamp": trade.closed_at,
                    "action": "SELL",
                    "price": float(trade.exit_price or trade.entry_price),
                }
            )
    return log


def run_strategy_backtest(
    strategy_id: str,
    params: dict[str, Any],
    candles: list[Candle],
    config: dict[str, Any],
) -> dict[str, Any]:
    initial_capital = float(config.get("initial_capital", 100_000.0))
    strategy = create_strategy(strategy_id, params)
    engine = ExecutionEngine()
    engine_result = engine.run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )
    context = RunContext(
        run_id=now_iso(),
        strategy_id=strategy_id,
        strategy_version="1",
        instrument=config["instrument"],
        timeframe=config["timeframe"],
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=initial_capital,
    )
    metrics = calculate_metrics_from_trade_log(engine_result["trade_log_report"], context)
    final = engine_result["final_portfolio"]
    meta = describe_strategy(strategy_id)
    deposit_pnl = float(metrics.deposit_baseline_pnl)

    return {
        "strategy_id": strategy_id,
        "strategy_version": "1",
        "title": meta.get("title", strategy_id),
        "status": "completed",
        "params": params,
        "parameter_specs": meta.get("parameters", []),
        "initial_capital": initial_capital,
        "metrics": {
            "total_pnl": float(metrics.total_pnl),
            "sharpe_ratio": float(metrics.sharpe_ratio),
            "max_drawdown": float(metrics.max_drawdown),
            "win_rate": float(metrics.win_rate),
            "deposit_baseline_pnl": deposit_pnl,
            "deposit_baseline_final": initial_capital + deposit_pnl,
        },
        "chart_points": build_chart_series(candles, engine_result["equity_curve"], initial_capital),
        "trade_log": build_trade_log(engine_result["trade_log"]),
        "final_portfolio": {
            "cash": float(final.cash),
            "position_size": float(final.position_size),
            "equity": float(final.equity),
        },
        "error": None,
    }


def set_strategy_running(dashboard: dict[str, Any], strategy_id: str, params: dict[str, Any]) -> None:
    entry = find_strategy_entry(dashboard, strategy_id)
    if entry is None:
        dashboard.setdefault("strategies", []).append(strategy_skeleton(strategy_id, params, "running"))
        return

    entry.update(
        {
            "status": "running",
            "params": params,
            "metrics": empty_metrics(),
            "chart_points": [],
            "trade_log": [],
            "final_portfolio": empty_portfolio(),
            "error": None,
        }
    )


def upsert_strategy_result(dashboard: dict[str, Any], result: dict[str, Any]) -> None:
    entry = find_strategy_entry(dashboard, result["strategy_id"])
    if entry is None:
        dashboard.setdefault("strategies", []).append(result)
        return

    entry.clear()
    entry.update(result)


def metrics_report_from_entry(entry: dict[str, Any], instrument: str) -> MetricsReport | None:
    if entry.get("status") != "completed":
        return None
    metrics = entry.get("metrics") or {}
    required = ("total_pnl", "sharpe_ratio", "max_drawdown", "win_rate", "deposit_baseline_pnl")
    if any(metrics.get(key) is None for key in required):
        return None
    try:
        return MetricsReport(
            strategy_id=str(entry["strategy_id"]),
            instrument=instrument,
            total_pnl=float(metrics["total_pnl"]),
            sharpe_ratio=float(metrics["sharpe_ratio"]),
            max_drawdown=float(metrics["max_drawdown"]),
            win_rate=float(metrics["win_rate"]),
            deposit_baseline_pnl=float(metrics["deposit_baseline_pnl"]),
        )
    except (TypeError, ValueError):
        return None


def ranking_entry_to_dict(entry: TopNEntry, previous_rank: int | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rank": entry.rank,
        "strategy_id": entry.strategy_id,
        "instrument": entry.instrument,
        "run_id": entry.run_id,
        "total_pnl": entry.total_pnl,
        "computed_at": entry.computed_at.isoformat(),
        "sharpe_ratio": entry.sharpe_ratio,
        "max_drawdown": entry.max_drawdown,
        "win_rate": entry.win_rate,
        "deposit_baseline_pnl": entry.deposit_baseline_pnl,
    }
    if previous_rank is not None and previous_rank != entry.rank:
        payload["previous_rank"] = previous_rank
        payload["rank_delta"] = previous_rank - entry.rank
    return payload


def update_dashboard_ranking(dashboard: dict[str, Any]) -> None:
    """Recompute strategy ranking from completed backtest metrics."""
    instrument = str(dashboard.get("instrument", "SBER"))
    strategies = dashboard.get("strategies") or []
    previous = {
        item["strategy_id"]: item["rank"]
        for item in (dashboard.get("ranking") or {}).get("entries") or []
        if item.get("strategy_id") is not None and item.get("rank") is not None
    }

    reports: list[MetricsReport | None] = []
    for entry in strategies:
        reports.append(metrics_report_from_entry(entry, instrument))

    top_n = build_top_n(
        reports,
        n=max(len(strategies), 1),
        config=RankingConfig(n=max(len(strategies), 1), require_above_baseline=False),
    )
    computed_at = now_iso()
    entries = [
        ranking_entry_to_dict(item, previous.get(item.strategy_id))
        for item in top_n
    ]
    dashboard["ranking"] = {"computed_at": computed_at, "entries": entries}


async def refresh_ranking() -> None:
    dashboard = load_dashboard()
    if not dashboard.get("strategies"):
        dashboard = default_dashboard()
    update_dashboard_ranking(dashboard)
    save_dashboard(dashboard)


async def bootstrap_all() -> None:
    config = load_config()
    dashboard = {
        "instrument": config["instrument"],
        "timeframe": config["timeframe"],
        "data_source": "T-Bank",
        "initial_capital": config.get("initial_capital", 100_000.0),
        "strategies": [
            strategy_skeleton(item["id"], dict(item["params"]), status="running")
            for item in config["strategies"]
        ],
        "ranking": empty_ranking(),
    }
    save_dashboard(dashboard)

    try:
        candles, data_source = await get_candles(config)
        dashboard["data_source"] = data_source
    except Exception as exc:
        for entry in dashboard["strategies"]:
            entry.update({"status": "error", "error": str(exc)})
        save_dashboard(dashboard)
        raise

    for item in config["strategies"]:
        strategy_id = item["id"]
        params = dict(item["params"])
        set_strategy_running(dashboard, strategy_id, params)
        save_dashboard(dashboard)
        try:
            result = run_strategy_backtest(strategy_id, params, candles, config)
            upsert_strategy_result(dashboard, result)
        except Exception as exc:
            entry = find_strategy_entry(dashboard, strategy_id)
            if entry:
                entry.update({"status": "error", "error": str(exc)})
        save_dashboard(dashboard)

    update_dashboard_ranking(dashboard)
    save_dashboard(dashboard)


async def run_single(strategy_id: str, params: dict[str, Any]) -> None:
    params = normalize_order_size(params)
    update_config_params(strategy_id, params)
    config = load_config()
    dashboard = load_dashboard()

    if not dashboard.get("strategies"):
        dashboard = default_dashboard()

    dashboard.update(
        {
            "instrument": config["instrument"],
            "timeframe": config["timeframe"],
            "initial_capital": config.get("initial_capital", 100_000.0),
        }
    )
    set_strategy_running(dashboard, strategy_id, params)
    save_dashboard(dashboard)

    try:
        candles, data_source = await get_candles(config)
        dashboard["data_source"] = data_source
        result = run_strategy_backtest(strategy_id, params, candles, config)
        upsert_strategy_result(dashboard, result)
    except Exception as exc:
        entry = find_strategy_entry(dashboard, strategy_id)
        if entry:
            entry.update({"status": "error", "error": str(exc)})
    update_dashboard_ranking(dashboard)
    save_dashboard(dashboard)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BackTestBench dashboard runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bootstrap", help="Run all configured strategies")
    sub.add_parser("refresh-ranking", help="Recompute strategy ranking from saved metrics")

    run_parser = sub.add_parser("run", help="Run a single strategy")
    run_parser.add_argument("strategy_id")
    run_parser.add_argument("params_json")

    return parser.parse_args()


def main() -> None:
    sanitize_config()
    repair_runtime_dashboard()
    args = parse_args()

    if args.command == "bootstrap":
        asyncio.run(bootstrap_all())
        return

    if args.command == "refresh-ranking":
        asyncio.run(refresh_ranking())
        return

    if args.command == "run":
        params = json.loads(args.params_json)
        asyncio.run(run_single(args.strategy_id, params))
        return

    asyncio.run(bootstrap_all())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc)
        sys.exit(1)
