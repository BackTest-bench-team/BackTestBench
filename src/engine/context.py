from dataclasses import dataclass
from typing import List

from .models import Candle
from .portfolio import Portfolio


@dataclass
class ExecutionContext:
    current_candle: Candle
    historical_candles: List[Candle]
    portfolio: Portfolio