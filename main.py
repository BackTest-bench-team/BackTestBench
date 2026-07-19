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

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import src.strategy.strategies  # noqa: F401 — register built-in strategies

from src.analytics import (
    RankingConfig,
    TopNEntry,
    build_optimizer_output,
    build_top_n,
    calculate_metrics_from_trade_log,
    rank_optimizer_results,
)
from src.analytics.metrics import metrics_to_dashboard_dict
from src.analytics.strategy_verdict import build_strategy_verdict, verdict_to_dashboard_dict
from src.backtest_config import (
    ConfigValidationError,
    ui_schema,
    validate_runtime_settings,
)
from src.broker_adapter.factory import build_adapter, source_display_name
from src.env_file import load_env_file_into_process, mask_token, read_env_file, write_env_file
from src.token_validation import validate_tokens_sync
from src.engine import ExecutionEngine, RunContext
from src.engine.execution_config import ExecutionConfig
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
BACKTEST_PENDING_FILE = DATA_DIR / "backtest.pending"
LIVE_RUN_FILE = DATA_DIR / "live-run.json"
LIVE_TICK_LOCK_FILE = DATA_DIR / "live-run.tick.lock"
MAX_CHART_POINTS = 300

LIVE_TICK_INTERVAL_SEC: dict[str, float] = {
    "1m": 15.0,
    "5m": 30.0,
    "15m": 60.0,
    "30m": 90.0,
    "1h": 120.0,
    "1d": 300.0,
    "1w": 600.0,
    "1M": 900.0,
}

RUNTIME_SETTING_KEYS = (
    "data_source",
    "instrument",
    "timeframe",
    "lookback_days",
    "initial_capital",
    "optimization_mode",
    "optimization_iterations",
    "optimization_seed",
    "commission_pct",
    "slippage_pct",
)

DATA_DIR.mkdir(exist_ok=True)

# Read-only CLI commands used by the dashboard on every page load.
# Skip dashboard repair/sanitize so VM does not parse the full runtime JSON.
LIGHTWEIGHT_COMMANDS = frozenset({
    "config-schema",
    "token-status",
    "set-strategy-enabled",
    "live-run-status",
    "live-run-start",
    "live-run-stop",
    "live-run-tick",
    "prepare-bootstrap",
})


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


def is_backtest_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return False

    if sys.platform == "win32":
        import ctypes

        process_query_limited = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        PID_FILE.unlink(missing_ok=True)
        return False

    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return False
    return True


def mark_backtest_pending() -> None:
    BACKTEST_PENDING_FILE.write_text(now_iso(), encoding="utf-8")


def clear_backtest_pending() -> None:
    BACKTEST_PENDING_FILE.unlink(missing_ok=True)


def is_backtest_active() -> bool:
    return BACKTEST_PENDING_FILE.exists() or is_backtest_running()


def load_live_run() -> dict[str, Any] | None:
    if not LIVE_RUN_FILE.exists():
        return None
    try:
        with open(LIVE_RUN_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        LIVE_RUN_FILE.unlink(missing_ok=True)
        return None
    if not isinstance(payload, dict) or not payload.get("strategy_id"):
        LIVE_RUN_FILE.unlink(missing_ok=True)
        return None
    return payload


def save_live_run(state: dict[str, Any]) -> None:
    LIVE_RUN_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def clear_live_run() -> None:
    LIVE_RUN_FILE.unlink(missing_ok=True)
    LIVE_TICK_LOCK_FILE.unlink(missing_ok=True)
    dashboard = load_dashboard() if DASHBOARD_FILE.exists() else None
    if not dashboard:
        return
    changed = False
    for entry in dashboard.get("strategies", []):
        if entry.pop("live_active", None):
            changed = True
    if changed:
        save_dashboard(dashboard)


def live_tick_min_interval_sec(timeframe: str) -> float:
    return float(LIVE_TICK_INTERVAL_SEC.get(str(timeframe), 60.0))


def _parse_iso_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _merge_live_strategy_result(
    dashboard: dict[str, Any],
    strategy_id: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    previous = find_strategy_entry(dashboard, strategy_id) or {}
    merged = dict(result)
    if previous.get("optimization"):
        merged["optimization"] = previous["optimization"]
    merged_params = dict(previous.get("params") or {})
    for key, value in (result.get("params") or {}).items():
        if key != "enabled":
            merged_params[key] = value
    if "enabled" in (previous.get("params") or {}):
        merged_params["enabled"] = previous["params"]["enabled"]
    merged["params"] = merged_params
    merged["live_active"] = True
    merged["status"] = "completed"
    merged["error"] = None
    return merged


def _live_status_payload() -> dict[str, Any]:
    if is_backtest_active():
        clear_live_run()
        return {"ok": True, "active": False, "stopped_reason": "backtest_started"}
    state = load_live_run()
    if not state:
        return {"ok": True, "active": False}
    return {
        "ok": True,
        "active": True,
        "strategy_id": state["strategy_id"],
        "started_at": state.get("started_at"),
        "last_tick_at": state.get("last_tick_at"),
    }


async def live_run_start_command(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json)
    strategy_id = str(payload["strategy_id"])
    params = strategy_run_params(dict(payload.get("params") or {}))

    if is_backtest_active():
        raise RuntimeError("Stop the running backtest before starting live refresh")

    existing = load_live_run()
    if existing and existing.get("strategy_id") != strategy_id:
        raise RuntimeError(
            f"Strategy {existing['strategy_id']} is already live. Stop it first."
        )

    state = {
        "strategy_id": strategy_id,
        "params": params,
        "started_at": now_iso(),
        "last_tick_at": None,
    }
    save_live_run(state)
    tick = await live_run_tick_command(force=True)
    if not tick.get("ok"):
        clear_live_run()
        raise RuntimeError(str(tick.get("message") or "Live refresh failed to start"))
    return {
        "ok": True,
        "active": True,
        "strategy_id": strategy_id,
        "strategy": tick.get("strategy"),
        "live": tick.get("live"),
    }


def live_run_stop_command(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json) if payload_json else {}
    state = load_live_run()
    if not state:
        return {"ok": True, "active": False}

    requested_id = payload.get("strategy_id")
    if requested_id and str(requested_id) != str(state.get("strategy_id")):
        raise RuntimeError("Another strategy is live")

    clear_live_run()
    return {"ok": True, "active": False, "strategy_id": state.get("strategy_id")}


def _live_tick_cached_response(
    state: dict[str, Any],
    config: dict[str, Any],
    *,
    message: str | None = None,
) -> dict[str, Any]:
    dashboard = load_dashboard() if DASHBOARD_FILE.exists() else default_dashboard()
    entry = find_strategy_entry(dashboard, str(state["strategy_id"]))
    timeframe = str(config.get("timeframe", "1h"))
    min_interval = live_tick_min_interval_sec(timeframe)
    next_tick_in_sec = min_interval
    last_tick_at = state.get("last_tick_at")
    if last_tick_at:
        elapsed = (datetime.now(timezone.utc) - _parse_iso_dt(last_tick_at)).total_seconds()
        next_tick_in_sec = max(0.0, min_interval - elapsed)
    payload: dict[str, Any] = {
        "ok": True,
        "active": True,
        "cached": True,
        "strategy": entry,
        "live": state,
        "next_tick_in_sec": next_tick_in_sec,
    }
    if message:
        payload["message"] = message
    return payload


async def live_run_tick_command(*, force: bool = False) -> dict[str, Any]:
    if is_backtest_active():
        clear_live_run()
        return {"ok": True, "active": False, "stopped_reason": "backtest_started"}

    state = load_live_run()
    if not state:
        return {"ok": True, "active": False}

    config = load_config()
    timeframe = str(config.get("timeframe", "1h"))
    min_interval = live_tick_min_interval_sec(timeframe)
    last_tick_at = state.get("last_tick_at")
    if not force and last_tick_at:
        elapsed = (datetime.now(timezone.utc) - _parse_iso_dt(last_tick_at)).total_seconds()
        if elapsed < min_interval:
            return _live_tick_cached_response(state, config)

    acquired = False
    for _ in range(300):
        try:
            fd = os.open(LIVE_TICK_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            acquired = True
            break
        except FileExistsError:
            import time

            time.sleep(0.1)
    if not acquired:
        return _live_tick_cached_response(
            state,
            config,
            message="Live refresh already in progress",
        )

    try:
        state = load_live_run()
        if not state:
            return {"ok": True, "active": False}
        if is_backtest_active():
            clear_live_run()
            return {"ok": True, "active": False, "stopped_reason": "backtest_started"}

        strategy_id = str(state["strategy_id"])
        params = strategy_run_params(dict(state.get("params") or {}))
        candles, source = await load_candles_for_backtest(config)
        result = run_fixed_params_backtest(strategy_id, params, candles, config)
        dashboard = load_dashboard() if DASHBOARD_FILE.exists() else default_dashboard()
        merged = _merge_live_strategy_result(dashboard, strategy_id, result)
        upsert_strategy_result(dashboard, merged)
        dashboard["data_source"] = source
        save_dashboard(dashboard)

        state["last_tick_at"] = now_iso()
        save_live_run(state)
    finally:
        LIVE_TICK_LOCK_FILE.unlink(missing_ok=True)

    return {
        "ok": True,
        "active": True,
        "cached": False,
        "strategy": merged,
        "live": state,
        "next_tick_in_sec": min_interval,
    }


def live_run_status_command() -> dict[str, Any]:
    return _live_status_payload()


def prepare_bootstrap_command() -> dict[str, Any]:
    clear_live_run()
    mark_backtest_pending()
    return {"ok": True, "live_cleared": True, "backtest_pending": True}


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


def strategy_enabled(params: dict[str, Any]) -> bool:
    """Whether the strategy participates in the next bootstrap run."""

    enabled = params.get("enabled", True)
    if isinstance(enabled, str):
        return enabled.strip().lower() not in {"0", "false", "no", "off"}
    return bool(enabled)


def strategy_run_params(params: dict[str, Any]) -> dict[str, Any]:
    """Strategy params passed to the engine (meta keys like enabled are stripped)."""

    return normalize_order_size({key: value for key, value in params.items() if key != "enabled"})


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
    previous = dict(overrides.get(strategy_id, {}))
    overrides[strategy_id] = {**previous, **params}
    config["strategy_overrides"] = overrides
    save_config(config)


def set_strategy_enabled(strategy_id: str, enabled: bool) -> dict[str, Any]:
    config = load_config()
    overrides = get_strategy_overrides(config)
    entry = dict(overrides.get(strategy_id, {}))
    entry["enabled"] = bool(enabled)
    overrides[strategy_id] = entry
    config["strategy_overrides"] = overrides
    save_config(config)

    dashboard = load_dashboard()
    entry_dashboard = find_strategy_entry(dashboard, strategy_id)
    if entry_dashboard is not None:
        merged = dict(entry_dashboard.get("params") or {})
        merged["enabled"] = bool(enabled)
        entry_dashboard["params"] = merged
        save_dashboard(dashboard)

    return {"strategy_id": strategy_id, "enabled": bool(enabled), "params": entry}


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
        "profit_factor": None,
        "calmar_ratio": None,
        "consistency_pct": None,
        "total_return_pct": None,
        "vs_buy_hold_pct": None,
        "positive_months": None,
        "total_months": None,
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
        "data_source": source_display_name(config.get("data_source", "tbank")),
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


async def load_candles_for_backtest(config: dict[str, Any]) -> tuple[list[Candle], str]:
    """Load candles via SQLite cache with chunked broker fetch for missing ranges."""

    from src.data_loader.backtest_fetch import ensure_backtest_candles
    from src.run_progress import write_run_progress

    from_dt, to_dt = get_candle_date_range(config)

    def on_fetch_progress(current: int, total: int) -> None:
        if current <= 0:
            label = f"Preparing {total} data requests"
        elif current >= total:
            label = "Candles loaded" if total <= 1 else f"Loaded candles {current}/{total}"
        else:
            label = f"Loading candles {current}/{total}"
        write_run_progress(
            phase="fetching",
            current=max(current, 0),
            total=total,
            label=label,
        )

    candles, source, _api_calls = await ensure_backtest_candles(
        config,
        from_dt,
        to_dt,
        fetch_candles_from_api,
        on_progress=on_fetch_progress,
    )
    return candles, source


async def get_candles(config: dict[str, Any]) -> tuple[list[Candle], str]:
    """Load candles from the broker (no SQLite cache)."""

    return await load_candles_for_backtest(config)


async def fetch_candles_from_api(
    config: dict[str, Any],
    from_dt: datetime,
    to_dt: datetime,
) -> list[Candle]:
    source = str(config.get("data_source", "tbank"))
    adapter = build_adapter(source, use_sandbox=False)
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


def downsample_chart_points(points: list[dict[str, Any]], max_points: int = MAX_CHART_POINTS) -> list[dict[str, Any]]:
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    indices = {min(len(points) - 1, int(i * step)) for i in range(max_points)}
    indices.add(len(points) - 1)
    return [points[i] for i in sorted(indices)]


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
    return downsample_chart_points(points)


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

    ranked_iterations = rank_optimizer_results(
        [(dict(item.params), item.metrics) for item in opt_result.iterations],
        config=RankingConfig(n=5, require_above_baseline=False),
    )
    optimizer_output = build_optimizer_output(
        opt_result.strategy_id,
        opt_result.instrument,
        ranked_iterations,
    )
    top_iterations = [
        {
            "rank": item.rank,
            "params": dict(item.params),
            "metrics": dict(row["metrics"]),
            # Backward-compatible flattened fields used by the current dashboard UI.
            "total_pnl": float(item.metrics.total_pnl),
            "sharpe_ratio": float(item.metrics.sharpe_ratio),
            "max_drawdown": float(item.metrics.max_drawdown),
            "win_rate": float(item.metrics.win_rate),
            "score": float(getattr(item.metrics, opt_result.target_metric, item.metrics.total_pnl)),
        }
        for item, row in zip(ranked_iterations, optimizer_output["ranked"])
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
        "strategy_id": optimizer_output["strategy_id"],
        "instrument": optimizer_output["instrument"],
        "ranked": optimizer_output["ranked"],
        "top_iterations": top_iterations,
    }


def create_execution_engine(config: dict[str, Any]) -> ExecutionEngine:
    return ExecutionEngine(ExecutionConfig.from_dashboard(config))


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
    chart_points = build_chart_series(candles, equity_curve, initial_capital)
    verdict = build_strategy_verdict(metrics, initial_capital=initial_capital)

    payload = {
        "strategy_id": strategy_id,
        "strategy_version": "1",
        "title": meta.get("title", strategy_id),
        "status": "completed",
        "params": params,
        "parameter_specs": meta.get("parameters", []),
        "initial_capital": initial_capital,
        "metrics": {
            **metrics_to_dashboard_dict(metrics),
            "deposit_baseline_final": initial_capital + deposit_pnl,
        },
        "verdict": verdict_to_dashboard_dict(verdict),
        "chart_points": chart_points,
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


def compute_run_metrics(
    trade_log_report: Any,
    run_context: RunContext,
    candles: list[Candle],
    equity_curve: list[float],
    initial_capital: float,
) -> MetricsReport:
    chart_points = build_chart_series(candles, equity_curve, initial_capital)
    return calculate_metrics_from_trade_log(
        trade_log_report,
        run_context,
        chart_points=chart_points,
    )


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
        opt_result = RandomSearchExecutionEngine(
            base_engine=create_execution_engine(config),
        ).run_optimization(
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
            strategy = create_strategy(strategy_id, params)
            engine_result = create_execution_engine(config).run(
                strategy=strategy,
                candles=candles,
                initial_capital=initial_capital,
            )
            metrics = compute_run_metrics(
                engine_result["trade_log_report"],
                run_context,
                candles,
                engine_result["equity_curve"],
                initial_capital,
            )
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

        best_params = normalize_order_size(dict(opt_result.best_params))
        update_config_params(strategy_id, best_params)
        best_metrics = compute_run_metrics(
            opt_result.best_trade_log_report,
            run_context,
            candles,
            opt_result.best_equity_curve,
            initial_capital,
        )
        return build_strategy_result(
            strategy_id,
            best_params,
            best_metrics,
            opt_result.best_equity_curve,
            opt_result.best_trade_log_report.trades,
            opt_result.best_final_portfolio,
            candles,
            config,
            optimization=build_optimization_summary(opt_result, param_grid, n_iterations, seed, mode),
        )

    strategy = create_strategy(strategy_id, params)
    engine_result = create_execution_engine(config).run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )
    metrics = compute_run_metrics(
        engine_result["trade_log_report"],
        run_context,
        candles,
        engine_result["equity_curve"],
        initial_capital,
    )
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
            profit_factor=float(metrics.get("profit_factor") or 0.0),
            calmar_ratio=float(metrics.get("calmar_ratio") or 0.0),
            consistency_pct=float(metrics.get("consistency_pct") or 0.0),
            total_return_pct=float(metrics.get("total_return_pct") or 0.0),
            vs_buy_hold_pct=float(metrics.get("vs_buy_hold_pct") or 0.0),
            positive_months=int(metrics.get("positive_months") or 0),
            total_months=int(metrics.get("total_months") or 0),
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
        config=RankingConfig(
            n=max(len(strategies), 1),
            require_above_baseline=False,
            initial_capital=float(dashboard.get("initial_capital", 100_000.0)),
        ),
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
    from src.run_progress import clear_run_progress, write_run_progress

    clear_live_run()
    mark_backtest_pending()
    clear_stop_request()
    write_run_pid()
    try:
        config = load_config()
        strategies = runtime_strategies(config)
        prev_dashboard = load_dashboard() if DASHBOARD_FILE.exists() else {}
        prev_entries = {
            entry.get("strategy_id"): entry
            for entry in prev_dashboard.get("strategies", [])
            if entry.get("strategy_id")
        }

        dashboard_strategies: list[dict[str, Any]] = []
        for item in strategies:
            strategy_id = item["id"]
            params = dict(item["params"])
            if "enabled" not in params:
                params["enabled"] = True
            previous = prev_entries.get(strategy_id)
            if strategy_enabled(params):
                dashboard_strategies.append(strategy_skeleton(strategy_id, params, status="running"))
            elif previous:
                kept = dict(previous)
                kept["params"] = params
                dashboard_strategies.append(kept)
            else:
                dashboard_strategies.append(strategy_skeleton(strategy_id, params, status="idle"))

        dashboard = {
            "instrument": config["instrument"],
            "timeframe": config["timeframe"],
            "data_source_key": str(config.get("data_source", "tbank")),
            "data_source": source_display_name(str(config.get("data_source", "tbank"))),
            "initial_capital": config.get("initial_capital", 100_000.0),
            "strategies": dashboard_strategies,
            "ranking": empty_ranking(),
        }
        save_dashboard(dashboard)

        enabled_strategies = [item for item in strategies if strategy_enabled(item["params"])]
        if not enabled_strategies:
            save_dashboard(dashboard)
            return

        total_strategies = len(enabled_strategies)
        progress_steps = max(total_strategies * 2, 1)
        progress_cursor = 0

        try:
            candles, source = await load_candles_for_backtest(config)
            if stop_requested():
                mark_strategies_stopped(dashboard)
                save_dashboard(dashboard)
                return
            dashboard["data_source"] = source
        except Exception as exc:
            for entry in dashboard["strategies"]:
                if entry.get("status") == "running":
                    entry.update({"status": "error", "error": str(exc)})
            save_dashboard(dashboard)
            raise

        write_run_progress(
            phase="backtesting",
            current=0,
            total=progress_steps,
            label="Starting backtests",
        )

        for index, item in enumerate(enabled_strategies, start=1):
            if stop_requested():
                mark_strategies_stopped(dashboard, from_strategy_id=item["id"])
                save_dashboard(dashboard)
                break

            strategy_id = item["id"]
            params = dict(item["params"])
            progress_cursor += 1
            write_run_progress(
                phase="backtesting",
                current=progress_cursor,
                total=progress_steps,
                label=f"Backtesting {strategy_id} ({index}/{total_strategies})",
                display_pct=round(100 * (progress_cursor - 0.5) / progress_steps),
            )
            set_strategy_running(dashboard, strategy_id, params)
            save_dashboard(dashboard)
            try:
                result = run_strategy_backtest(
                    strategy_id,
                    strategy_run_params(params),
                    candles,
                    config,
                )
                result["params"] = params
                upsert_strategy_result(dashboard, result)
            except Exception as exc:
                entry = find_strategy_entry(dashboard, strategy_id)
                if entry:
                    status = "idle" if str(exc) == "Stopped by user" else "error"
                    entry.update({"status": status, "error": str(exc)})
            save_dashboard(dashboard)
            progress_cursor += 1
            write_run_progress(
                phase="backtesting",
                current=progress_cursor,
                total=progress_steps,
                label=f"Completed {strategy_id} ({index}/{total_strategies})",
            )

        update_dashboard_ranking(dashboard)
        save_dashboard(dashboard)
    finally:
        clear_run_pid()
        clear_backtest_pending()
        clear_stop_request()
        clear_run_progress()


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


def token_status_command() -> dict[str, Any]:
    load_env_file_into_process(override=True)
    stored = read_env_file()
    tokens: dict[str, Any] = {}
    for key in ("TINKOFF_TOKEN", "TWELVEDATA_TOKEN"):
        value = os.getenv(key) or stored.get(key)
        tokens[key] = {
            "configured": bool(value and str(value).strip()),
            "masked": mask_token(str(value).strip() if value else None),
        }
    return {"ok": True, "tokens": tokens}


def save_tokens_command(payload_json: str) -> dict[str, Any]:
    payload = json.loads(payload_json)
    updates: dict[str, str] = {}
    if payload.get("tinkoff_token"):
        updates["TINKOFF_TOKEN"] = str(payload["tinkoff_token"]).strip()
    if payload.get("twelvedata_token"):
        updates["TWELVEDATA_TOKEN"] = str(payload["twelvedata_token"]).strip()
    if not updates:
        raise ValueError("Provide tinkoff_token and/or twelvedata_token")

    verify = bool(payload.get("verify", True))
    if verify:
        validation = validate_tokens_sync(updates)
        failed = {
            key: {
                "configured": False,
                "valid": False,
                "message": result["message"],
                "masked": None,
            }
            for key, result in validation.items()
            if not result.get("valid")
        }
        if failed:
            return {"ok": False, "tokens": failed, "message": next(iter(failed.values()))["message"]}

    write_env_file(updates)
    load_env_file_into_process(override=True)

    tokens: dict[str, Any] = {}
    if verify:
        validation = validate_tokens_sync(updates)
        for key, result in validation.items():
            tokens[key] = {
                "configured": True,
                "valid": True,
                "message": result["message"],
                "masked": mask_token(updates.get(key) or os.getenv(key)),
            }
    else:
        for key, value in updates.items():
            tokens[key] = {
                "configured": True,
                "valid": None,
                "message": "Saved to .env",
                "masked": mask_token(value),
            }

    return {"ok": True, "tokens": tokens}


def run_fixed_params_backtest(
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
    strategy = create_strategy(strategy_id, strategy_run_params(dict(params)))
    engine_result = create_execution_engine(config).run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )
    metrics = compute_run_metrics(
        engine_result["trade_log_report"],
        run_context,
        candles,
        engine_result["equity_curve"],
        initial_capital,
    )
    return build_strategy_result(
        strategy_id,
        strategy_run_params(dict(params)),
        metrics,
        engine_result["equity_curve"],
        engine_result["trade_log"],
        engine_result["final_portfolio"],
        candles,
        config,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BackTestBench dashboard runner")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("bootstrap", help="Run all configured strategies")
    sub.add_parser("refresh-ranking", help="Recompute strategy ranking from saved metrics")
    sub.add_parser("stop", help="Request stop of a running backtest")
    sub.add_parser("config-schema", help="Print UI schema for dashboard settings")

    save_parser = sub.add_parser("save-settings", help="Validate and save runtime settings")
    save_parser.add_argument("settings_json")

    sub.add_parser("token-status", help="Print configured API token status from .env")

    save_tokens_parser = sub.add_parser("save-tokens", help="Validate and save API tokens to .env")
    save_tokens_parser.add_argument("payload_json")

    add_strategy_parser = sub.add_parser("add-strategy", help="Validate and save a composable strategy YAML")
    add_strategy_parser.add_argument("payload_json")

    delete_strategy_parser = sub.add_parser("delete-strategy", help="Delete a composable strategy YAML")
    delete_strategy_parser.add_argument("strategy_id")

    set_enabled_parser = sub.add_parser("set-strategy-enabled", help="Toggle strategy participation in bootstrap")
    set_enabled_parser.add_argument("payload_json")

    live_start_parser = sub.add_parser("live-run-start", help="Start live refresh for one strategy")
    live_start_parser.add_argument("payload_json")

    live_stop_parser = sub.add_parser("live-run-stop", help="Stop live refresh")
    live_stop_parser.add_argument("payload_json")

    sub.add_parser("live-run-status", help="Print live refresh status")
    sub.add_parser("live-run-tick", help="Refresh live strategy metrics from broker API")
    sub.add_parser("prepare-bootstrap", help="Stop live refresh and mark backtest pending")

    return parser.parse_args()


def main() -> None:
    load_env_file_into_process()
    args = parse_args()
    if args.command not in LIGHTWEIGHT_COMMANDS:
        sanitize_config()
        repair_runtime_dashboard()

    if args.command == "bootstrap":
        asyncio.run(bootstrap_all())
        return

    if args.command == "stop":
        request_stop()
        return

    if args.command == "config-schema":
        print(json.dumps({"settings": load_config(), "schema": ui_schema()}, ensure_ascii=False))
        return

    if args.command == "token-status":
        print(json.dumps(token_status_command(), ensure_ascii=False))
        return

    if args.command == "save-tokens":
        try:
            result = save_tokens_command(args.payload_json)
        except (ValueError, json.JSONDecodeError) as exc:
            print(str(exc))
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        if not result.get("ok"):
            sys.exit(1)
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

    if args.command == "set-strategy-enabled":
        try:
            payload = json.loads(args.payload_json)
            result = set_strategy_enabled(str(payload["strategy_id"]), bool(payload.get("enabled", True)))
        except (ValueError, json.JSONDecodeError, KeyError) as exc:
            print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps({"ok": True, **result}, ensure_ascii=False))
        return

    if args.command == "live-run-start":
        try:
            result = asyncio.run(live_run_start_command(args.payload_json))
        except (ValueError, json.JSONDecodeError, RuntimeError) as exc:
            print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.command == "live-run-stop":
        try:
            result = live_run_stop_command(args.payload_json)
        except (ValueError, json.JSONDecodeError, RuntimeError) as exc:
            print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.command == "live-run-status":
        print(json.dumps(live_run_status_command(), ensure_ascii=False))
        return

    if args.command == "live-run-tick":
        try:
            result = asyncio.run(live_run_tick_command())
        except RuntimeError as exc:
            print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        print(json.dumps(result, ensure_ascii=False))
        return

    if args.command == "prepare-bootstrap":
        print(json.dumps(prepare_bootstrap_command(), ensure_ascii=False))
        return

    asyncio.run(bootstrap_all())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc)
        sys.exit(1)
