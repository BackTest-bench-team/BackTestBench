"""
Broker Adapter Module.

This module provides unified access to market data and trading operations
across different brokers through a common interface.
"""

from .base import (
    BrokerAdapter,
    BrokerError,
    AuthenticationError,
    InvalidInstrumentError,
    RateLimitError,
    InsufficientFundsError,
    InvalidAccountError
)
from .models import (
    Candle,
    OrderResult,
    Position,
    Portfolio
)
from .tbank import TBankAdapter
from .twelvedata import TwelveDataAdapter
from .bybit import BybitAdapter
__all__ = [
    # Base interface
    'BrokerAdapter',
    # Concrete adapters
    'TBankAdapter',
    'TwelveDataAdapter',
    'BybitAdapter',
    # Exceptions
    'BrokerError',
    'AuthenticationError',
    'InvalidInstrumentError',
    'RateLimitError',
    'InsufficientFundsError',
    'InvalidAccountError',
    # Models
    'Candle',
    'OrderResult',
    'Position',
    'Portfolio'
]

