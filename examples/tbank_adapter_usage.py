"""
T-Bank Broker Adapter - Simple API for fetching real market data.

Usage:
    from examples.tbank_adapter_usage import fetch_candles, run_backtest
    
    # Fetch candles
    candles = asyncio.run(fetch_candles(
        instrument="SBER",
        timeframe="1h",
        days=30
    ))
    
    # Or run full backtest
    result = run_backtest(
        instrument="SBER",
        timeframe="1h",
        days=30,
        initial_capital=100000,
        strategy_params={"fast": 10, "slow": 30, "order_size": 1.0}
    )
    
Token is loaded from .env file (TINKOFF_TOKEN variable).
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load token from .env file
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False, verbose=True)

from src.broker_adapter import TBankAdapter
from src.engine.models import Candle


def get_token() -> str:
    """Load T-Bank API token from .env file."""
    token = os.getenv("TINKOFF_TOKEN")
    if not token:
        raise ValueError(
            "TINKOFF_TOKEN not found in .env file. "
            "Please add TINKOFF_TOKEN=your_token_here to .env"
        )
    return token


async def fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> List[Candle]:
    """
    Fetch real historical candles from T-Bank Invest API.
    
    Args:
        instrument: Ticker symbol (e.g., "SBER", "GAZP", "LKOH")
        timeframe: Candle timeframe ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M")
        days: Number of days of history (default: 7)
        from_date: Start date in format "YYYY-MM-DD" (optional, overrides days)
        to_date: End date in format "YYYY-MM-DD" (optional, defaults to now)
        use_sandbox: Use sandbox environment (default: False)
        token: API token (optional, loads from .env if not provided)
    
    Returns:
        List of Candle objects with real market data
    """
    if token is None:
        token = get_token()
    
    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    else:
        to_dt = datetime.now()
    
    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    else:
        from_dt = to_dt - timedelta(days=days)
    
    adapter = TBankAdapter(
        token=token,
        use_sandbox=use_sandbox,
        verify_ssl=False,
    )
    
    async with adapter:
        candles = await adapter.get_candles(
            instrument=instrument,
            timeframe=timeframe,
            from_dt=from_dt,
            to_dt=to_dt,
        )
    
    return candles


def run_fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> List[Candle]:
    """Synchronous wrapper for fetch_candles."""
    return asyncio.run(fetch_candles(
        instrument=instrument,
        timeframe=timeframe,
        days=days,
        from_date=from_date,
        to_date=to_date,
        use_sandbox=use_sandbox,
        token=token,
    ))


def run_backtest(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 30,
    initial_capital: float = 100000.0,
    strategy_params: Optional[Dict[str, Any]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch candles and run backtest with MA Crossover strategy.
    
    Args:
        instrument: Ticker symbol (e.g., "SBER", "GAZP")
        timeframe: Candle timeframe ("1h", "1d", etc.)
        days: Number of days of history
        initial_capital: Starting capital for backtest
        strategy_params: Strategy parameters (default: fast=10, slow=30, order_size=1.0)
        from_date: Start date "YYYY-MM-DD" (optional)
        to_date: End date "YYYY-MM-DD" (optional)
        use_sandbox: Use sandbox environment
        token: API token (optional, loads from .env if not provided)
    
    Returns:
        Dict with "trade_log", "final_portfolio", "candles_count"
    """
    from src.engine.execution_engine import ExecutionEngine
    from src.strategy.strategies.ma_crossover import MACrossover
    
    # Fetch candles
    candles = run_fetch_candles(
        instrument=instrument,
        timeframe=timeframe,
        days=days,
        from_date=from_date,
        to_date=to_date,
        use_sandbox=use_sandbox,
        token=token,
    )
    
    if not candles:
        return {"trade_log": [], "final_portfolio": None, "candles_count": 0}
    
    # Default strategy params
    if strategy_params is None:
        strategy_params = {"fast": 10, "slow": 30, "order_size": 1.0}
    
    # Create strategy and engine
    strategy = MACrossover(params=strategy_params)
    engine = ExecutionEngine()
    
    # Run backtest
    result = engine.run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )
    
    result["candles_count"] = len(candles)
    return result


if __name__ == "__main__":
    print("Example 1: Fetch candles only")
    
    candles = run_fetch_candles(
        instrument="SBER",
        timeframe="1h",
        days=7,
    )
    
    print(f"Fetched {len(candles)} candles")
    for c in candles[:5]:
        print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} C={c.close} V={c.volume}")
    
    print()
    print("Example 2: Full backtest with MA Crossover")
    
    result = run_backtest(
        instrument="SBER",
        timeframe="1h",
        days=30,
        initial_capital=100000,
        strategy_params={"fast": 10, "slow": 30, "order_size": 1.0},
    )
    
    print(f"Candles: {result['candles_count']}")
    print(f"Trades: {len(result['trade_log'])}")
    for trade in result['trade_log'][:5]:
        print(f"  {trade.timestamp}: PnL={trade.pnl:+.2f}")
    
    if result['final_portfolio']:
        print(f"Final equity: {result['final_portfolio'].equity:.2f}")

