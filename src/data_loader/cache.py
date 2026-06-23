"""Optional in-memory cache for frequently accessed candles."""
from collections import OrderedDict
from typing import Optional, List
from src.db.models import CandleModel

class CandleCache:
    def __init__(self, max_size: int = 1000):
        self._cache = OrderedDict()
        self._max_size = max_size

    def _key(self, instrument: str, timeframe: str) -> str:
        return f"{instrument}:{timeframe}"

    def get(self, instrument: str, timeframe: str) -> Optional[List[CandleModel]]:
        return self._cache.get(self._key(instrument, timeframe))

    def set(self, instrument: str, timeframe: str, candles: List[CandleModel]):
        key = self._key(instrument, timeframe)
        if len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = candles

    def clear(self):
        self._cache.clear()
