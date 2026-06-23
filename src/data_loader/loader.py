"""
Data Loader: receives List[Candle] from Broker Adapter and stores them in DB.
Supports explicit date-range loading with optional caching.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.db.session import SessionLocal
from src.db.models import CandleModel
from src.engine.models import Candle
from src.data_loader.validator import validate_candles
from src.data_loader.cache import CandleCache

class DataLoader:
    def __init__(self, use_cache: bool = False):
        self.session = SessionLocal()
        self.use_cache = use_cache
        self.cache = CandleCache() if use_cache else None

    def store_candles(self, instrument: str, timeframe: str, candles: List[Candle]) -> int:
        """
        Saves list of candles. if candle with such (instrument, timeframe, timestamp)
        exists, then update it's OHLCV. Return number of changes.
        """
        if not candles:
            return 0
        validate_candles(candles)

        values = [
            {
                "instrument": instrument,
                "timeframe": timeframe,
                "timestamp": datetime.fromisoformat(c.timestamp),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": int(c.volume) if c.volume else 0,
            }
            for c in candles
        ]

        if "postgresql" in str(self.session.bind.url):
            stmt = pg_insert(CandleModel).values(values)
            update_cols = {
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument", "timeframe", "timestamp"],
                set_=update_cols,
            )
        else:  # SQLite fallback
            stmt = sqlite_insert(CandleModel).values(values)
            update_cols = {
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument", "timeframe", "timestamp"],
                set_=update_cols,
            )

        result = self.session.execute(stmt)
        self.session.commit()

        # Clear cache
        if self.cache:
            self.cache.clear()
        return result.rowcount

    def load_candles(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[CandleModel]:
        """
        Load candles in some interval
        Firsly checks cache.
        """
        if self.cache:
            cached = self.cache.get(instrument, timeframe)
            if cached:
                # Easy filter through cache interval
                return [
                    c for c in cached
                    if start <= c.timestamp <= end
                ]

        stmt = (
            select(CandleModel)
            .where(
                and_(
                    CandleModel.instrument == instrument,
                    CandleModel.timeframe == timeframe,
                    CandleModel.timestamp >= start,
                    CandleModel.timestamp <= end,
                )
            )
            .order_by(CandleModel.timestamp.asc())
        )
        rows = self.session.execute(stmt).scalars().all()
        if self.cache:
            self.cache.set(instrument, timeframe, rows)
        return rows

    def close(self):
        self.session.close()
