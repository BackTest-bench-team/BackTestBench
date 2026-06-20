"""
Data models for Broker Adapter module.

This module defines the common data structures used across all broker adapters,
including the Candle model and related types.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List


@dataclass
class Candle:
    """
    Standard candle model used throughout the system.
    
    Represents a single OHLCV (Open, High, Low, Close, Volume) candle
    for a specific instrument and timeframe.
    
    Attributes:
        instrument: Instrument ticker symbol (e.g., 'SBER', 'AAPL')
        timestamp: Candle start time in UTC
        timeframe: Candle timeframe ('1m', '5m', '1h', '1d', etc.)
        open: Opening price
        high: Highest price during the period
        low: Lowest price during the period
        close: Closing price
        volume: Trading volume (number of shares/contracts)
        adjusted_close: Optional adjusted close price (for corporate actions)
    """
    instrument: str
    timestamp: datetime
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    adjusted_close: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert candle to dictionary for serialization."""
        return {
            'instrument': self.instrument,
            'timestamp': self.timestamp.isoformat(),
            'timeframe': self.timeframe,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'adjusted_close': self.adjusted_close
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Candle':
        """Create candle from dictionary."""
        return cls(
            instrument=data['instrument'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            timeframe=data['timeframe'],
            open=float(data['open']),
            high=float(data['high']),
            low=float(data['low']),
            close=float(data['close']),
            volume=float(data['volume']),
            adjusted_close=data.get('adjusted_close')
        )


@dataclass
class OrderResult:
    """
    Result of a trading order placement.
    
    Attributes:
        order_id: Unique order identifier
        status: Order status ('pending', 'executed', 'cancelled', 'failed')
        executed_price: Actual execution price (if executed)
        executed_quantity: Actual executed quantity
        message: Additional information or error message
    """
    order_id: str
    status: str
    executed_price: Optional[float] = None
    executed_quantity: Optional[float] = None
    message: Optional[str] = None


@dataclass
class Position:
    """
    Represents a single position in a portfolio.
    
    Attributes:
        instrument: Instrument ticker
        quantity: Number of shares/contracts held
        average_price: Average entry price
        current_price: Current market price
        market_value: Current market value of position
    """
    instrument: str
    quantity: float
    average_price: float
    current_price: float
    market_value: float


@dataclass
class Portfolio:
    """
    Client's portfolio containing all positions and cash.
    
    Attributes:
        account_id: Account identifier
        cash: Available cash balance
        positions: List of positions
        total_value: Total portfolio value (cash + positions)
    """
    account_id: str
    cash: float
    positions: List[Position]
    total_value: float
