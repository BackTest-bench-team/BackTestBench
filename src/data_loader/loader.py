"""
Data Loader: receives List[Candle] from Broker Adapter and stores them in DB.
Supports explicit date-range loading with optional in-memory caching.
"""
from datetime import datetime, timezone
from typing import List

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.data_loader.cache import CandleCache
from src.data_loader.validator import ValidationError, prepare_candles
from src.db.models import CandleModel
from src.db.session import SessionLocal
from src.engine.models import Candle


def utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def candle_to_db_timestamp(timestamp: str) -> datetime:
    return utc_naive(datetime.fromisoformat(timestamp))


_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def candle_model_to_engine(row: CandleModel) -> Candle:
    ts = utc_naive(row.timestamp)
    return Candle(
        timestamp=ts.strftime("%Y-%m-%dT%H:%M:%S"),
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=float(row.volume or 0),
    )


class DataLoader:
    def __init__(self, use_cache: bool = False):
        self.session = SessionLocal()
        self.use_cache = use_cache
        self.cache = CandleCache() if use_cache else None

    def store_candles(self, instrument: str, timeframe: str, candles: List[Candle]) -> int:
        """Upsert candles by (instrument, timeframe, timestamp). Returns affected row count."""
        if not candles:
            return 0
        candles = prepare_candles(candles)
        if not candles:
            raise ValidationError("No valid candles after filtering")

        values = [
            {
                "instrument": instrument,
                "timeframe": timeframe,
                "timestamp": candle_to_db_timestamp(c.timestamp),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": int(c.volume) if c.volume else 0,
            }
            for c in candles
        ]

        insert_fn = pg_insert if "postgresql" in str(self.session.bind.url) else sqlite_insert
        stmt = insert_fn(CandleModel).values(values)
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
        start_naive = utc_naive(start)
        end_naive = utc_naive(end)

        if self.cache:
            cached = self.cache.get(instrument, timeframe)
            if cached:
                return [
                    c
                    for c in cached
                    if start_naive <= utc_naive(c.timestamp) <= end_naive
                ]

        stmt = (
            select(CandleModel)
            .where(
                and_(
                    CandleModel.instrument == instrument,
                    CandleModel.timeframe == timeframe,
                    CandleModel.timestamp >= start_naive,
                    CandleModel.timestamp <= end_naive,
                )
            )
            .order_by(CandleModel.timestamp.asc())
        )
        rows = self.session.execute(stmt).scalars().all()
        if self.cache:
            self.cache.set(instrument, timeframe, rows)
        return rows

    def get_latest_candle_timestamp(
        self,
        instrument: str,
        timeframe: str,
    ) -> datetime | None:
        stmt = (
            select(CandleModel.timestamp)
            .where(
                and_(
                    CandleModel.instrument == instrument,
                    CandleModel.timeframe == timeframe,
                )
            )
            .order_by(CandleModel.timestamp.desc())
            .limit(1)
        )
        row = self.session.execute(stmt).scalar_one_or_none()
        if row is None:
            return None
        latest = utc_naive(row)
        return latest.replace(tzinfo=timezone.utc)

    def load_engine_candles(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        return [candle_model_to_engine(row) for row in self.load_candles(instrument, timeframe, start, end)]

    def has_sufficient_data(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        min_ratio: float = 0.5,
    ) -> bool:
        """True when DB/cache already covers most of the requested range."""
        rows = self.load_candles(instrument, timeframe, start, end)
        if len(rows) < 10:
            return False
        bar_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
        span_seconds = (utc_naive(end) - utc_naive(start)).total_seconds()
        expected = max(span_seconds / bar_seconds, 1)
        return len(rows) >= expected * min_ratio

    def close(self):
        self.session.close()
