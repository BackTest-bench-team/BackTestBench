from dataclasses import dataclass
from typing import List

from engine.models import Candle
from engine.portfolio import Portfolio


@dataclass
class ExecutionContext:
    current_candle: Candle
    historical_candles: List[Candle]
    portfolio: Portfolio