"""
Data Loader: receives List[Candle] from Broker Adapter and stores them in DB.
Supports explicit date-range loading.
"""
from datetime import datetime
from typing import List
from sqlalchemy import select, and_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.db.session import SessionLocal
from src.db.models import CandleModel
from src.engine.models import Candle
from src.data_loader.validator import validate_candles


class DataLoader:
    def __init__(self):
        self.session = SessionLocal()

    def store_candles(self, instrument: str, timeframe: str, candles: List[Candle]) -> int:
        """Saves candles in DB. Saves OHLCV if conflicts."""
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
                "volume": int(c.volume),
            }
            for c in candles
        ]

        stmt = sqlite_insert(CandleModel).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["instrument", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            }
        )

        result = self.session.execute(stmt)
        self.session.commit()
        return result.rowcount

    def load_candles(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[CandleModel]:

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
        return list(self.session.execute(stmt).scalars().all())

    def close(self):
        self.session.close()
