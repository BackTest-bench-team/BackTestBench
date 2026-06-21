"""
Base abstract class for Broker Adapter.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

try:
    from .models import Candle, OrderResult, Portfolio
except ImportError:
    # Handle circular import or missing models
    Candle = None
    OrderResult = None
    Portfolio = None


class BrokerAdapter(ABC):
    """Abstract base class for all broker adapters."""
    
    @abstractmethod
    async def get_candles(
        self,
        instrument: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List['Candle']:
        """Retrieve historical candles for an instrument."""
        pass
    
    @abstractmethod
    async def place_order(
        self,
        instrument: str,
        action: str,
        quantity: float,
        price: Optional[float] = None
    ) -> 'OrderResult':
        """Place a trading order."""
        pass
    
    @abstractmethod
    async def get_portfolio(
        self,
        account_id: Optional[str] = None
    ) -> 'Portfolio':
        """Retrieve client's portfolio."""
        pass
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


class BrokerError(Exception):
    """Base exception."""
    pass


class AuthenticationError(BrokerError):
    """Authentication failed."""
    pass


class InvalidInstrumentError(BrokerError):
    """Invalid instrument."""
    pass


class RateLimitError(BrokerError):
    """Rate limit exceeded."""
    pass


class InsufficientFundsError(BrokerError):
    """Insufficient funds."""
    pass


class InvalidAccountError(BrokerError):
    """Invalid account."""
    pass
