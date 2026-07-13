import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.analytics import calculate_validation_metrics_from_trade_log
from src.analytics.validation import ValidationMetricsReport
from src.broker_adapter import build_adapter, BrokerError
from src.data_loader import DataLoader
from src.engine.context import ExecutionContext
from src.engine.execution_engine import ExecutionEngine
from src.engine.models import Candle, RunContext
from src.strategy import create_strategy


def load_bot_params(config_or_json_path: str | Path) -> Dict[str, Any]:
    """Loads strategy parameters from an optimizer JSON report or a regular config."""
    path = Path(config_or_json_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл конфигурации не найден: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "best_params" in data:
        return data["best_params"]
    if isinstance(data, dict) and "params" in data:
        return data["params"]

    return data


def fetch_recent_market_data_via_loader(
    instrument: str,
    timeframe: str = "1h",
    days: int = 7,
    source: str = "tbank",
    use_sandbox: bool = True,
    token: Optional[str] = None
) -> List[Candle]:
    """
    Loads the latest market data using the project's official DataLoader.
    If data for the requested period is already available in the database/cache,
    no broker request is made.
    """
    async def _fetch():
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=days)

        # 1. Prepare the broker adapter for downloading data (if not already in the database)
        adapter_kwargs = {"use_sandbox": use_sandbox} if source == "tbank" else {}
        if token:
            adapter_kwargs["token"] = token
        
        adapter = build_adapter(source, **adapter_kwargs)

        # 2. Create an adapter function matching the callback format expected by DataLoader
        async def _broker_fetcher(start: datetime, end: datetime) -> List[Candle]:
            async with adapter:
                return await adapter.get_candles(
                    instrument=instrument,
                    timeframe=timeframe,
                    from_dt=start,
                    to_dt=end
                )

        # 3. Load data via DataLoader (it normalizes, removes duplicates, and stores data in the database)
        loader = DataLoader(use_cache=True)
        try:
            market_data = await loader.ensure_candles_loaded(
                instrument=instrument,
                timeframe=timeframe,
                start=start_dt,
                end=now,
                fetch=_broker_fetcher,
                broker_label=source.upper()
            )
            print(f"[DataLoader] Источник свежих данных: {market_data.source}")
            return market_data.candles
        finally:
            loader.close()

    try:
        return asyncio.run(_fetch())
    except Exception as e:
        raise BrokerError(f"Ошибка интеграции DataLoader и {source}: {e}") from e


class MinimalTradingBot:
    """Minimal trading bot (Validation Run Engine)."""

    def __init__(
        self,
        base_engine: Optional[ExecutionEngine] = None,
        order_callback: Optional[Callable[[str, str, float, float], None]] = None
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
        source_backtest_run_id: str = "optimizer_best"
    ) -> ValidationMetricsReport:
        """Runs the strategy on recent market data and generates a validation report."""
        if not recent_candles:
            raise ValueError("Для запуска бота необходим хотя бы небольшой срез свечей.")

        # 1. Create the strategy using the optimized parameters
        strategy = create_strategy(strategy_id, params)

        # 2. Execute it through the standard ExecutionEngine (no duplicated simulation!)
        raw_result = self.engine.run(strategy, recent_candles, initial_capital)

        # 3. Build the execution context
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

        # 4. Compute the ValidationMetricsReport only (according to the project scope)
        validation_report = calculate_validation_metrics_from_trade_log(
            trade_log=raw_result["trade_log_report"],
            context=context,
            source_backtest_run_id=source_backtest_run_id
        )

        # 5. Check trades for Paper Trading (risk-free order simulation)
        self._check_and_log_paper_orders(raw_result["trade_log_report"].trades, instrument)

        return validation_report

    def _check_and_log_paper_orders(self, trades: list, instrument: str) -> None:
        """Logs simulated orders (Paper Trading mode) to the console."""
        if not trades:
            print(f"[Paper Bot] На свежем срезе данных для {instrument} новых сделок не открывалось.")
            return

        last_trade = trades[-1]
        print(f"[Paper Bot] Зафиксирована торговая активность по {instrument}:")
        print(f"   -> Вход: price={last_trade.entry_price}, qty={last_trade.quantity}")
        if last_trade.exit_price:
            print(f"   -> Выход: price={last_trade.exit_price}, P&L={last_trade.pnl:.2f}")

        if self.order_callback:
            action = "BUY" if last_trade.quantity > 0 else "SELL"
            self.order_callback(instrument, action, abs(last_trade.quantity), last_trade.entry_price)


def run_trading_bot(
    strategy_id: str,
    config_path: str,
    instrument: str,
    recent_candles: Optional[List[Candle]] = None,
    initial_capital: float = 100_000.0,
    timeframe: str = "1h",
    days_to_fetch: int = 7,
    broker_source: str = "tbank",
    use_sandbox: bool = True
) -> ValidationMetricsReport:
    """Entrypoint. Uses DataLoader to fetch the latest market data."""
    params = load_bot_params(config_path)

    # If candles are not provided explicitly, fetch them via DataLoader
    if recent_candles is None:
        print(f"[Bot Orchestrator] Запрос свежих данных для {instrument} за {days_to_fetch} дн. через DataLoader...")
        recent_candles = fetch_recent_market_data_via_loader(
            instrument=instrument,
            timeframe=timeframe,
            days=days_to_fetch,
            source=broker_source,
            use_sandbox=use_sandbox
        )
        print(f"[Bot Orchestrator] В работу передано {len(recent_candles)} валидированных свечей!")

    bot = MinimalTradingBot()
    return bot.run_validation(
        strategy_id=strategy_id,
        params=params,
        recent_candles=recent_candles,
        initial_capital=initial_capital,
        instrument=instrument,
        timeframe=timeframe
    )