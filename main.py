import argparse
import asyncio
import json
import os
import signal
import subprocess
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
from src.backtest_config import (
    ConfigValidationError,
    ui_schema,
    validate_runtime_settings,
)
from src.broker_adapter import TBankAdapter
from src.data_loader import DataLoader, LoadedMarketData
from src.db import init_db
from src.engine import ExecutionEngine, RunContext
from src.engine.models import Candle, MetricsReport, Trade
from src.engine.optimization_engine import RandomSearchExecutionEngine
from src.engine.portfolio import Portfolio
from src.strategy import create_strategy, describe_strategy, get_optimize_spec, get_strategy_class
from src.strategy_manifest import (
    StrategyManifestError,
    add_strategy_yaml,
    delete_strategy_yaml,
    get_strategy_overrides,
    runtime_strategies,
)
from src.strategy.registry import unregister_strategy
from src.strategy.schema import ORDER_SIZE_MAX

DATA_DIR = BASE_DIR / "data"
CONFIG_FILE = BASE_DIR / "config" / "dashboard.json"
DASHBOARD_FILE = DATA_DIR / "runtime-dashboard.json"
STOP_FILE = DATA_DIR / "backtest.stop"
PID_FILE = DATA_DIR / "backtest.pid"

RUNTIME_SETTING_KEYS = (
    "instrument",
    "timeframe",
    "lookback_days",
    "initial_capital",
    "optimization_mode",
    "optimization_iterations",
    "optimization_seed",
)

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


def clear_stop_request() -> None:
    STOP_FILE.unlink(missing_ok=True)


def stop_requested() -> bool:
    return STOP_FILE.exists()


def request_stop() -> None:
    STOP_FILE.parent.mkdir(exist_ok=True)
    STOP_FILE.write_text(now_iso(), encoding="utf-8")

    if DASHBOARD_FILE.exists():
        dashboard = load_dashboard()
        mark_strategies_stopped(dashboard)
        save_dashboard(dashboard)

    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return

    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                check=False,
                capture_output=True,
            )
            return
        except OSError:
            pass

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass


def write_run_pid() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def clear_run_pid() -> None:
    PID_FILE.unlink(missing_ok=True)


def save_runtime_settings(updates: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    payload = {key: updates.get(key, config.get(key)) for key in RUNTIME_SETTING_KEYS}
    validated = validate_runtime_settings(payload)
    config.update(validated)
    save_config(config)
    return config


def mark_strategies_stopped(dashboard: dict[str, Any], from_strategy_id: str | None = None) -> None:
    cancel = from_strategy_id is None
    for entry in dashboard.get("strategies", []):
        if not cancel and entry.get("strategy_id") == from_strategy_id:
            cancel = True
        if cancel and entry.get("status") == "running":
            entry.update({"status": "idle", "error": "Stopped by user"})


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
    """Fix saved strategy param overrides in config/dashboard.json."""
    config = load_config()
    overrides = get_strategy_overrides(config)
    changed = False
    for strategy_id, params in list(overrides.items()):
        fixed = normalize_order_size(params)
        if fixed != params:
            overrides[strategy_id] = fixed
            changed = True
    if changed:
        config["strategy_overrides"] = overrides
        save_config(config)


def get_strategy_overrides(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = config.get("strategy_overrides")
    if not isinstance(raw, dict):
        return {}
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}


def update_config_params(strategy_id: str, params: dict[str, Any]) -> None:
    params = normalize_order_size(params)
    config = load_config()
    overrides = get_strategy_overrides(config)
    overrides[strategy_id] = params
    config["strategy_overrides"] = overrides
    save_config(config)


def sync_dashboard_strategies(dashboard: dict[str, Any], config: dict[str, Any]) -> None:
    configured = {item["id"]: item["params"] for item in runtime_strategies(config)}
    existing = {entry.get("strategy_id"): entry for entry in dashboard.get("strategies", [])}

    strategies: list[dict[str, Any]] = []
    for strategy_id, params in configured.items():
        if strategy_id in existing:
            strategies.append(existing[strategy_id])
        else:
            strategies.append(strategy_skeleton(strategy_id, params, status="idle"))

    dashboard["strategies"] = strategies


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
        config = load_config()
        sync_dashboard_strategies(data, config)
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
    dashboard = {
        "instrument": config.get("instrument", "SBER"),
        "timeframe": config.get("timeframe", "1h"),
        "data_source": "T-Bank",
        "initial_capital": config.get("initial_capital", 100_000.0),
        "strategies": [],
        "ranking": empty_ranking(),
        "last_updated": None,
    }
    sync_dashboard_strategies(dashboard, config)
    return dashboard


def find_strategy_entry(dashboard: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    for entry in dashboard.get("strategies", []):
        if entry.get("strategy_id") == strategy_id:
            return entry
    return None


def get_candle_date_range(
    config: dict[str, Any],
    period_end: datetime | None = None,
) -> tuple[datetime, datetime]:
    if period_end is not None:
        to_dt = period_end
    elif explicit := config.get("period_end"):
        to_dt = datetime.fromisoformat(str(explicit).replace("Z", "+00:00"))
        if to_dt.tzinfo is None:
            to_dt = to_dt.replace(tzinfo=timezone.utc)
    else:
        to_dt = datetime.now(timezone.utc)

    from_dt = to_dt - timedelta(days=int(config.get("lookback_days", 30)))
    return from_dt, to_dt


async def load_market_data(
    config: dict[str, Any],
    loader: DataLoader | None = None,
) -> tuple[DataLoader, LoadedMarketData]:
    """Load candles once via DataLoader; reuse loader cache for in-process reads."""
    init_db()
    instrument = config["instrument"]
    timeframe = config["timeframe"]
    owns_loader = loader is None
    loader = loader or DataLoader(use_cache=True)

    latest = loader.get_latest_candle_timestamp(instrument, timeframe)
    period_end = latest if latest is not None and not config.get("period_end") else None
    from_dt, to_dt = get_candle_date_range(config, period_end=period_end)

    async def fetch(from_dt: datetime, to_dt: datetime) -> list[Candle]:
        return await fetch_candles_from_api(config, from_dt, to_dt)

    try:
        market_data = await loader.ensure_candles_loaded(
            instrument,
            timeframe,
            from_dt,
            to_dt,
            fetch,
        )
        if not market_data.candles:
            raise RuntimeError("No candles available for backtest window")
        return loader, market_data
    except Exception:
        if owns_loader:
            loader.close()
        raise


async def get_candles(
    config: dict[str, Any],
    loader: DataLoader | None = None,
) -> tuple[list[Candle], str]:
    """Load candles: read from DB when fresh, otherwise fetch from T-Bank and store."""
    active_loader, market_data = await load_market_data(config, loader=loader)
    if loader is None:
        active_loader.close()
    return market_data.candles, market_data.source


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


def strategy_supports_optimization(strategy_id: str) -> bool:
    cls = get_strategy_class(strategy_id)
    definition = getattr(cls, "_DEFINITION", None)
    if definition is None:
        return False
    return bool(get_optimize_spec(definition).params)


def build_optimization_grid(strategy_id: str, base_params: dict[str, Any]) -> dict[str, Any]:
    cls = get_strategy_class(strategy_id)
    definition = getattr(cls, "_DEFINITION", None)
    if definition is None:
        return dict(base_params)

    grid: dict[str, Any] = {}
    for pname, pdef in definition.params.items():
        if pdef.optimizable and pdef.choices:
            grid[pname] = list(pdef.choices)
        else:
            grid[pname] = base_params.get(pname, pdef.default)
    return grid


def build_optimization_summary(
    opt_result: Any,
    param_grid: dict[str, Any],
    n_iterations: int,
    seed: int,
    mode: str,
) -> dict[str, Any]:
    search_lists = [v for v in param_grid.values() if isinstance(v, (list, tuple)) and len(v) > 0]
    grid_size = 1
    for values in search_lists:
        grid_size *= len(values)

    sorted_iters = sorted(opt_result.iterations, key=lambda item: item.score, reverse=True)
    top_iterations = [
        {
            "params": dict(item.params),
            "total_pnl": float(item.metrics.total_pnl),
            "sharpe_ratio": float(item.metrics.sharpe_ratio),
            "score": float(item.score),
        }
        for item in sorted_iters[:5]
    ]

    exhaustive = mode == "grid" or grid_size <= n_iterations

    return {
        "target_metric": opt_result.target_metric,
        "mode": mode,
        "grid_size": grid_size,
        "iterations_requested": n_iterations,
        "iterations_run": opt_result.total_iterations_run,
        "exhaustive": exhaustive,
        "seed": seed,
        "top_iterations": top_iterations,
    }


def build_strategy_result(
    strategy_id: str,
    params: dict[str, Any],
    metrics: MetricsReport,
    equity_curve: list[float],
    trades: list[Trade],
    final: Portfolio,
    candles: list[Candle],
    config: dict[str, Any],
    optimization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    initial_capital = float(config.get("initial_capital", 100_000.0))
    meta = describe_strategy(strategy_id)
    deposit_pnl = float(metrics.deposit_baseline_pnl)

    payload = {
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
        "chart_points": build_chart_series(candles, equity_curve, initial_capital),
        "trade_log": build_trade_log(trades),
        "final_portfolio": {
            "cash": float(final.cash),
            "position_size": float(final.position_size),
            "equity": float(final.equity),
        },
        "error": None,
    }
    if optimization is not None:
        payload["optimization"] = optimization
    return payload


def run_strategy_backtest(
    strategy_id: str,
    params: dict[str, Any],
    candles: list[Candle],
    config: dict[str, Any],
) -> dict[str, Any]:
    initial_capital = float(config.get("initial_capital", 100_000.0))
    run_context = RunContext(
        run_id=now_iso(),
        strategy_id=strategy_id,
        strategy_version="1",
        instrument=config["instrument"],
        timeframe=config["timeframe"],
        period_start=candles[0].timestamp,
        period_end=candles[-1].timestamp,
        initial_capital=initial_capital,
    )

    if strategy_supports_optimization(strategy_id):
        param_grid = build_optimization_grid(strategy_id, params)
        n_iterations = int(config.get("optimization_iterations", 16))
        seed = int(config.get("optimization_seed", 42))
        mode = str(config.get("optimization_mode", "grid"))
        opt_result = RandomSearchExecutionEngine().run_optimization(
            strategy_id=strategy_id,
            param_grid=param_grid,
            candles=candles,
            initial_capital=initial_capital,
            run_context=run_context,
            n_iterations=n_iterations,
            target_metric="total_pnl",
            seed=seed,
            mode=mode,
            should_stop=stop_requested,
        )
        if stop_requested():
            raise RuntimeError("Stopped by user")
        if opt_result.best_metrics is None:
            raise RuntimeError("Optimization found no valid parameter combination with trades")

        best_params = normalize_order_size(dict(opt_result.best_params))
        update_config_params(strategy_id, best_params)
        return build_strategy_result(
            strategy_id,
            best_params,
            opt_result.best_metrics,
            opt_result.best_equity_curve,
            opt_result.best_trade_log_report.trades,
            opt_result.best_final_portfolio,
            candles,
            config,
            optimization=build_optimization_summary(opt_result, param_grid, n_iterations, seed, mode),
        )

    strategy = create_strategy(strategy_id, params)
    engine_result = ExecutionEngine().run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )
    metrics = calculate_metrics_from_trade_log(engine_result["trade_log_report"], run_context)
    return build_strategy_result(
        strategy_id,
        params,
        metrics,
        engine_result["equity_curve"],
        engine_result["trade_log"],
        engine_result["final_portfolio"],
        candles,
        config,
    )


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
    clear_stop_request()
    write_run_pid()
    loader: DataLoader | None = None
    try:
        config = load_config()
        strategies = runtime_strategies(config)
        dashboard = {
            "instrument": config["instrument"],
            "timeframe": config["timeframe"],
            "data_source": "T-Bank",
            "initial_capital": config.get("initial_capital", 100_000.0),
            "strategies": [
                strategy_skeleton(item["id"], dict(item["params"]), status="running")
                for item in strategies
            ],
            "ranking": empty_ranking(),
        }
        save_dashboard(dashboard)

        loader = DataLoader(use_cache=True)
        try:
            _, market_data = await load_market_data(config, loader=loader)
            if stop_requested():
                mark_strategies_stopped(dashboard)
                save_dashboard(dashboard)
                return
            candles = market_data.candles
            dashboard["data_source"] = market_data.source
        except Exception as exc:
            for entry in dashboard["strategies"]:
                entry.update({"status": "error", "error": str(exc)})
            save_dashboard(dashboard)
            raise

        for item in strategies:
            if stop_requested():
                mark_strategies_stopped(dashboard, from_strategy_id=item["id"])
                save_dashboard(dashboard)
                break

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
                    status = "idle" if str(exc) == "Stopped by user" else "error"
                    entry.update({"status": status, "error": str(exc)})
            save_dashboard(dashboard)

        update_dashboard_ranking(dashboard)
        save_dashboard(dashboard)
    finally:
        if loader is not None:
            loader.close()
        clear_run_pid()
        clear_stop_request()


def add_strategy_from_yaml(yaml_text: str) -> dict[str, Any]:
    manifest = add_strategy_yaml(yaml_text)
    dashboard = load_dashboard()
    sync_dashboard_strategies(dashboard, load_config())
    save_dashboard(dashboard)
    return manifest


def delete_strategy_command(strategy_id: str) -> dict[str, Any]:
    deleted_file = delete_strategy_yaml(strategy_id)
    unregister_strategy(strategy_id)

    config = load_config()
    overrides = get_strategy_overrides(config)
    overrides.pop(strategy_id, None)
    config["strategy_overrides"] = overrides
    save_config(config)

    dashboard = load_dashboard()
    dashboard["strategies"] = [
        entry
        for entry in dashboard.get("strategies", [])
        if entry.get("strategy_id") != strategy_id
    ]
    ranking = dashboard.get("ranking") or empty_ranking()
    ranking["entries"] = [
        entry
        for entry in ranking.get("entries", [])
        if entry.get("strategy_id") != strategy_id
    ]
    dashboard["ranking"] = ranking
    save_dashboard(dashboard)

    return {"deleted": strategy_id, "file": deleted_file}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BackTestBench dashboard runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bootstrap", help="Run all configured strategies")
    sub.add_parser("refresh-ranking", help="Recompute strategy ranking from saved metrics")
    sub.add_parser("stop", help="Request stop of a running backtest")
    sub.add_parser("config-schema", help="Print UI schema for dashboard settings")

    save_parser = sub.add_parser("save-settings", help="Validate and save runtime settings")
    save_parser.add_argument("settings_json")

    add_strategy_parser = sub.add_parser("add-strategy", help="Validate and save a composable strategy YAML")
    add_strategy_parser.add_argument("payload_json")

    delete_strategy_parser = sub.add_parser("delete-strategy", help="Delete a composable strategy YAML")
    delete_strategy_parser.add_argument("strategy_id")

    return parser.parse_args()


def main() -> None:
    sanitize_config()
    repair_runtime_dashboard()
    args = parse_args()

    if args.command == "bootstrap":
        asyncio.run(bootstrap_all())
        return

    if args.command == "stop":
        request_stop()
        return

    if args.command == "config-schema":
        print(json.dumps({"settings": load_config(), "schema": ui_schema()}, ensure_ascii=False))
        return

    if args.command == "save-settings":
        try:
            updates = json.loads(args.settings_json)
            config = save_runtime_settings(updates)
        except ConfigValidationError as exc:
            print(str(exc))
            sys.exit(1)
        print(json.dumps(config, ensure_ascii=False))
        return

    if args.command == "add-strategy":
        try:
            payload = json.loads(args.payload_json)
            yaml_text = payload.get("yaml", "")
            if not isinstance(yaml_text, str) or not yaml_text.strip():
                raise StrategyManifestError("YAML text is required")
            manifest = add_strategy_from_yaml(yaml_text)
        except (StrategyManifestError, json.JSONDecodeError) as exc:
            print(str(exc))
            sys.exit(1)
        print(json.dumps({"ok": True, "strategy": manifest}, ensure_ascii=False))
        return

    if args.command == "delete-strategy":
        try:
            result = delete_strategy_command(args.strategy_id)
        except StrategyManifestError as exc:
            print(str(exc))
            sys.exit(1)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return

    if args.command == "refresh-ranking":
        asyncio.run(refresh_ranking())
        return

    asyncio.run(bootstrap_all())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc)
        sys.exit(1)
