"""
Data models for Broker Adapter module.

This module defines the common data structures used across all broker adapters.
Uses the unified Candle model from src.engine.models.
"""

from dataclasses import dataclass
from typing import Optional, List

# Re-export unified Candle model from engine
from src.engine.models import Candle, Signal, Trade


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

