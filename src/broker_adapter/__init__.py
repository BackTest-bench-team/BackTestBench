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
from .factory import (
    OPTIONAL_TOKEN_SOURCES,
    SUPPORTED_SOURCES,
    TOKEN_ENV_BY_SOURCE,
    build_adapter,
    get_token,
    resolve_source,
    source_display_name,
    token_configured,
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
    # Factory
    'SUPPORTED_SOURCES',
    'TOKEN_ENV_BY_SOURCE',
    'OPTIONAL_TOKEN_SOURCES',
    'build_adapter',
    'get_token',
    'resolve_source',
    'source_display_name',
    'token_configured',
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

