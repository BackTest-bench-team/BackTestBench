"""
Example: Using T-Bank Broker Adapter with REAL DATA
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.broker_adapter import TBankAdapter, Candle
from src.broker_adapter.base import AuthenticationError, InvalidInstrumentError, RateLimitError


async def fetch_real_candles(
    token: str,
    instrument: str,
    timeframe: str,
    days: int = 7,
    use_sandbox: bool = False,
) -> List[Candle]:
    """Fetch REAL historical candles from T-Bank Invest API."""
    to_dt = datetime.now()
    from_dt = to_dt - timedelta(days=days)
    
    adapter = TBankAdapter(
        token=token,
        use_sandbox=use_sandbox,
        verify_ssl=False,
    )
    
    try:
        async with adapter:
            print(f"[OK] Connected to T-Bank Invest API")
            print(f"Fetching {timeframe} candles for {instrument}...")
            print(f"Period: {from_dt.strftime('%Y-%m-%d')} to {to_dt.strftime('%Y-%m-%d')}")
            print()
            
            candles = await adapter.get_candles(
                instrument=instrument,
                timeframe=timeframe,
                from_dt=from_dt,
                to_dt=to_dt,
            )
            
            return candles
            
    except AuthenticationError as e:
        print(f"[FAIL] Authentication failed: {e}")
        return []
    except InvalidInstrumentError as e:
        print(f"[FAIL] Invalid instrument: {e}")
        return []
    except RateLimitError as e:
        print(f"[FAIL] Rate limit exceeded: {e}")
        return []
    except Exception as e:
        print(f"[FAIL] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


async def display_candles(candles: List[Candle], limit: int = 15):
    """Display candles in a formatted table."""
    if not candles:
        print("No candles to display")
        return
    
    print(f"  Retrieved {len(candles)} REAL candles from T-Bank Invest API")
    
    print(f"\nShowing first {min(limit, len(candles))} candles:")
    print(f"{'Timestamp':<22} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>15}")
    
    for candle in candles[:limit]:
        ts = candle.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        print(
            f"{ts:<22} "
            f"{candle.open:>10.2f} "
            f"{candle.high:>10.2f} "
            f"{candle.low:>10.2f} "
            f"{candle.close:>10.2f} "
            f"{candle.volume:>15,.0f}"
        )
    
    if len(candles) > limit:
        print(f"\n... and {len(candles) - limit} more candles")
    
    if candles:
        closes = [c.close for c in candles]
        print(f"\n--- Summary for {candles[0].instrument} ---")
        print(f"  Period: {candles[0].timestamp.strftime('%Y-%m-%d')} to {candles[-1].timestamp.strftime('%Y-%m-%d')}")
        print(f"  First close: {closes[0]:.2f}")
        print(f"  Last close:  {closes[-1]:.2f}")
        change = closes[-1] - closes[0]
        change_pct = (change / closes[0]) * 100
        print(f"  Change: {change:+.2f} ({change_pct:+.2f}%)")
        print(f"  Min close: {min(closes):.2f}")
        print(f"  Max close: {max(closes):.2f}")
        avg_volume = sum(c.volume for c in candles) / len(candles)
        print(f"  Avg volume: {avg_volume:,.0f}")


async def main():
    """Main function to demonstrate real data fetching."""
    
    # Your REAL T-Bank Invest API token
    TOKEN = os.getenv("TINKOFF_TOKEN", "t.lgU5v7QUGFemc0xErTRcLV6jw7nyT0tF_UDmMFFu7r72dqgTpwL6rGbi9MnUNJdCR55HLjJrM_G9FxOYlolW5A")
    
    # Set to True if your token is for sandbox
    USE_SANDBOX = False
    
    print("  T-Bank Invest API - REAL DATA PARSER".center(95))
    print()
    
    if not TOKEN:
        print("ERROR: No token provided!")
        return
    
    # Example 1: SBER (Sberbank) - hourly candles
    print("  Example 1: SBER (Sberbank) - Hourly Candles (Last 7 days)")
    
    candles = await fetch_real_candles(
        token=TOKEN,
        instrument="SBER",
        timeframe="1h",
        days=7,
        use_sandbox=USE_SANDBOX,
    )
    await display_candles(candles, limit=10)
    
    # Example 2: GAZP (Gazprom) - daily candles
    print("\n\n")
    print("  Example 2: GAZP (Gazprom) - Daily Candles (Last 30 days)")
    
    candles = await fetch_real_candles(
        token=TOKEN,
        instrument="GAZP",
        timeframe="1d",
        days=30,
        use_sandbox=USE_SANDBOX,
    )
    await display_candles(candles, limit=10)
    

if __name__ == "__main__":
    asyncio.run(main())
