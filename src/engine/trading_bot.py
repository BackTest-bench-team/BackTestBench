"""Minimal trading bot — out-of-sample validation on recent market data (PR #144)."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.analytics import calculate_validation_metrics_from_trade_log
from src.analytics.validation import ValidationMetricsReport
from src.broker_adapter import BrokerError, build_adapter
from src.broker_adapter.factory import TOKEN_ENV_BY_SOURCE
from src.data_loader import DataLoader
from src.engine.execution_engine import ExecutionEngine
from src.engine.models import Candle, RunContext, Trade
from src.strategy import create_strategy


def load_bot_params(config_or_json_path: str | Path) -> Dict[str, Any]:
    """Load strategy parameters from an optimizer JSON report or a regular config."""
    path = Path(config_or_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict) and "best_params" in data:
        return dict(data["best_params"])
    if isinstance(data, dict) and "params" in data:
        return dict(data["params"])

    return dict(data) if isinstance(data, dict) else {}


async def fetch_recent_market_data_via_loader_async(
    instrument: str,
    timeframe: str = "1h",
    days: int = 7,
    source: str = "tbank",
    use_sandbox: bool = True,
    token: Optional[str] = None,
    *,
    force_fetch: bool = False,
) -> tuple[List[Candle], str]:
    """Load recent candles via DataLoader (optionally forcing a broker refresh)."""
    now = datetime.now(timezone.utc)
    start_dt = now - timedelta(days=days)

    adapter_kwargs: dict[str, Any] = {"use_sandbox": use_sandbox} if source == "tbank" else {}
    if token:
        adapter_kwargs["token"] = token

    adapter = build_adapter(source, **adapter_kwargs)

    async def _broker_fetcher(start: datetime, end: datetime) -> List[Candle]:
        async with adapter:
            return await adapter.get_candles(
                instrument=instrument,
                timeframe=timeframe,
                from_dt=start,
                to_dt=end,
            )

    loader = DataLoader(use_cache=True)
    try:
        market_data = await loader.ensure_candles_loaded(
            instrument=instrument,
            timeframe=timeframe,
            start=start_dt,
            end=now,
            fetch=_broker_fetcher,
            broker_label=source.upper(),
            token_env=TOKEN_ENV_BY_SOURCE.get(source, "TINKOFF_TOKEN"),
            force_fetch=force_fetch,
        )
        return market_data.candles, market_data.source
    finally:
        loader.close()


def fetch_recent_market_data_via_loader(
    instrument: str,
    timeframe: str = "1h",
    days: int = 7,
    source: str = "tbank",
    use_sandbox: bool = True,
    token: Optional[str] = None,
    *,
    force_fetch: bool = False,
) -> List[Candle]:
    """Sync wrapper used by ``run_trading_bot``. Do not call inside a running event loop."""

    async def _fetch() -> List[Candle]:
        candles, _source = await fetch_recent_market_data_via_loader_async(
            instrument=instrument,
            timeframe=timeframe,
            days=days,
            source=source,
            use_sandbox=use_sandbox,
            token=token,
            force_fetch=force_fetch,
        )
        print(f"[DataLoader] Fresh data source: {_source}")
        return candles

    try:
        return asyncio.run(_fetch())
    except Exception as exc:
        raise BrokerError(f"DataLoader integration failed for {source}: {exc}") from exc


def _trade_to_dict(trade: Trade) -> dict[str, Any]:
    return {
        "entry_price": float(trade.entry_price),
        "exit_price": float(trade.exit_price) if trade.exit_price is not None else None,
        "quantity": float(trade.quantity),
        "pnl": float(trade.pnl),
        "opened_at": trade.opened_at,
        "closed_at": trade.closed_at,
    }


@dataclass(frozen=True)
class ValidationRunSnapshot:
    """UI/job snapshot built on top of ``run_validation()``."""

    report: ValidationMetricsReport
    trade_count: int
    candles_loaded: int
    candle_source: str
    period_start: str | None
    period_end: str | None
    last_trade: dict[str, Any] | None
    paper_events: list[str]
    chart_points: list[dict[str, Any]]
    trade_log: list[dict[str, Any]]


BOT_POLL_SECONDS: dict[str, int] = {
    "1m": 30,
    "5m": 60,
    "15m": 120,
    "1h": 180,
    "4h": 300,
    "1d": 600,
}


def poll_seconds_for_timeframe(timeframe: str) -> int:
    return BOT_POLL_SECONDS.get(timeframe, 120)


def build_validation_chart_points(
    candles: List[Candle],
    equity_curve: list[float],
    initial_capital: float,
) -> list[dict[str, Any]]:
    if not candles or len(equity_curve) < 2 or initial_capital <= 0:
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


def build_validation_trade_log(trades: list[Trade]) -> list[dict[str, Any]]:
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


class MinimalTradingBot:
    """Minimal trading bot (validation run engine, PR #144)."""

    def __init__(
        self,
        base_engine: Optional[ExecutionEngine] = None,
        order_callback: Optional[Callable[[str, str, float, float], None]] = None,
    ):
        self.engine = base_engine or ExecutionEngine()
        self.order_callback = order_callback

    def run_validation(
        self,
        strategy_id: str,
        params: Dict[str, Any],
        recent_candles: List[Candle],
        initial_capital: float,
        instrument: str,
        timeframe: str = "1h",
        source_backtest_run_id: str = "optimizer_best",
    ) -> ValidationMetricsReport:
        """Run the strategy on recent market data and return a validation report."""
        return self._execute_validation(
            strategy_id=strategy_id,
            params=params,
            recent_candles=recent_candles,
            initial_capital=initial_capital,
            instrument=instrument,
            timeframe=timeframe,
            source_backtest_run_id=source_backtest_run_id,
        ).report

    def validation_snapshot(
        self,
        strategy_id: str,
        params: Dict[str, Any],
        recent_candles: List[Candle],
        initial_capital: float,
        instrument: str,
        timeframe: str = "1h",
        source_backtest_run_id: str = "optimizer_best",
        candle_source: str = "",
    ) -> ValidationRunSnapshot:
        """UI/job helper that wraps ``run_validation`` with chart and trade details."""
        return self._execute_validation(
            strategy_id=strategy_id,
            params=params,
            recent_candles=recent_candles,
            initial_capital=initial_capital,
            instrument=instrument,
            timeframe=timeframe,
            source_backtest_run_id=source_backtest_run_id,
            candle_source=candle_source,
        )

    def _execute_validation(
        self,
        strategy_id: str,
        params: Dict[str, Any],
        recent_candles: List[Candle],
        initial_capital: float,
        instrument: str,
        timeframe: str = "1h",
        source_backtest_run_id: str = "optimizer_best",
        candle_source: str = "",
    ) -> ValidationRunSnapshot:
        if not recent_candles:
            raise ValueError("At least one candle is required to run the bot.")

        strategy = create_strategy(strategy_id, params)
        raw_result = self.engine.run(strategy, recent_candles, initial_capital)
        trades = list(raw_result["trade_log_report"].trades)
        equity_curve = list(raw_result["equity_curve"])

        now_iso = datetime.now(timezone.utc).isoformat()
        context = RunContext(
            run_id=f"bot_val_{now_iso}",
            strategy_id=strategy_id,
            strategy_version="1",
            instrument=instrument,
            timeframe=timeframe,
            period_start=recent_candles[0].timestamp,
            period_end=recent_candles[-1].timestamp,
            initial_capital=initial_capital,
        )

        validation_report = calculate_validation_metrics_from_trade_log(
            trade_log=raw_result["trade_log_report"],
            context=context,
            source_backtest_run_id=source_backtest_run_id,
        )

        paper_events = self._check_and_log_paper_orders(trades, instrument)
        last_trade = _trade_to_dict(trades[-1]) if trades else None
        return ValidationRunSnapshot(
            report=validation_report,
            trade_count=len(trades),
            candles_loaded=len(recent_candles),
            candle_source=candle_source,
            period_start=recent_candles[0].timestamp,
            period_end=recent_candles[-1].timestamp,
            last_trade=last_trade,
            paper_events=paper_events,
            chart_points=build_validation_chart_points(
                recent_candles, equity_curve, initial_capital
            ),
            trade_log=build_validation_trade_log(trades),
        )

    def _check_and_log_paper_orders(self, trades: list[Trade], instrument: str) -> list[str]:
        events: list[str] = []
        if not trades:
            message = f"[Paper Bot] No new trades on the fresh slice for {instrument}."
            print(message)
            events.append(message)
            return events

        last_trade = trades[-1]
        print(f"[Paper Bot] Activity on {instrument}:")
        print(f"   -> Entry: price={last_trade.entry_price}, qty={last_trade.quantity}")
        if last_trade.exit_price is not None:
            print(f"   -> Exit: price={last_trade.exit_price}, P&L={last_trade.pnl:.2f}")

        events.append(
            f"Activity on {instrument}: entry {last_trade.entry_price}, qty {last_trade.quantity}"
        )
        if last_trade.exit_price is not None:
            events.append(f"Exit {last_trade.exit_price}, P&L {last_trade.pnl:.2f}")

        if self.order_callback:
            action = "BUY" if last_trade.quantity > 0 else "SELL"
            self.order_callback(
                instrument, action, abs(last_trade.quantity), last_trade.entry_price
            )

        return events


def run_trading_bot(
    strategy_id: str,
    config_path: str,
    instrument: str,
    recent_candles: Optional[List[Candle]] = None,
    initial_capital: float = 100_000.0,
    timeframe: str = "1h",
    days_to_fetch: int = 7,
    broker_source: str = "tbank",
    use_sandbox: bool = True,
) -> ValidationMetricsReport:
    """Entrypoint from PR #144. Uses DataLoader to fetch the latest market data."""
    params = load_bot_params(config_path)

    if recent_candles is None:
        print(
            f"[Bot Orchestrator] Fetching fresh data for {instrument} "
            f"over {days_to_fetch}d via DataLoader..."
        )
        recent_candles = fetch_recent_market_data_via_loader(
            instrument=instrument,
            timeframe=timeframe,
            days=days_to_fetch,
            source=broker_source,
            use_sandbox=use_sandbox,
        )
        print(f"[Bot Orchestrator] Loaded {len(recent_candles)} validated candles.")

    bot = MinimalTradingBot()
    return bot.run_validation(
        strategy_id=strategy_id,
        params=params,
        recent_candles=recent_candles,
        initial_capital=initial_capital,
        instrument=instrument,
        timeframe=timeframe,
    )
