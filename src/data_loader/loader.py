"""Load broker candles into SQLite and serve them to the engine."""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.data_loader.cache import CandleCache
from src.data_loader.models import PriceBar
from src.data_loader.validator import validate_candles
from src.db.models import CandleModel
from src.db.session import SessionLocal
from src.engine.models import Candle

_TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


def utc_naive(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def candle_to_db_timestamp(timestamp: str) -> datetime:
    return utc_naive(datetime.fromisoformat(timestamp))


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


def candle_model_to_price_bar(row: CandleModel) -> PriceBar:
    candle = candle_model_to_engine(row)
    return PriceBar(timestamp=candle.timestamp, price=float(candle.close))


@dataclass(frozen=True, slots=True)
class LoadedMarketData:
    """Candles and composable price series for one lookback window."""

    candles: list[Candle]
    price_series: list[PriceBar]
    source: str


class DataLoader:
    def __init__(self, use_cache: bool = False):
        self.session = SessionLocal()
        self.use_cache = use_cache
        self.cache = CandleCache() if use_cache else None

    def _release_db_transaction(self) -> None:
        """End the implicit read transaction so parallel jobs can write to SQLite."""
        self.session.commit()

    def store_candles(self, instrument: str, timeframe: str, candles: List[Candle]) -> int:
        """Normalize, validate, and upsert candles by (instrument, timeframe, timestamp)."""
        cleaned = validate_candles(candles)

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
            for c in cleaned
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
        *,
        last_n_bars: int | None = None,
    ) -> List[CandleModel]:
        start_naive = utc_naive(start)
        end_naive = utc_naive(end)

        if self.cache:
            cached = self.cache.get(instrument, timeframe)
            if cached:
                rows = [
                    row
                    for row in cached
                    if start_naive <= utc_naive(row.timestamp) <= end_naive
                ]
                return rows[-last_n_bars:] if last_n_bars and last_n_bars > 0 else rows

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
        rows = list(self.session.execute(stmt).scalars().all())
        if last_n_bars and last_n_bars > 0:
            rows = rows[-last_n_bars:]
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
        *,
        last_n_bars: int | None = None,
    ) -> List[Candle]:
        rows = self.load_candles(
            instrument, timeframe, start, end, last_n_bars=last_n_bars
        )
        return [candle_model_to_engine(row) for row in rows]

    def load_price_series(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        *,
        last_n_bars: int | None = None,
    ) -> list[PriceBar]:
        """Export (timestamp, close) bars for composable strategies."""
        rows = self.load_candles(
            instrument, timeframe, start, end, last_n_bars=last_n_bars
        )
        return [candle_model_to_price_bar(row) for row in rows]

    async def ensure_candles_loaded(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        fetch: Callable[[datetime, datetime], Awaitable[list[Candle]]],
        *,
        min_ratio: float = 0.5,
        broker_label: str = "T-Bank",
        token_env: str = "TINKOFF_TOKEN",
        force_fetch: bool = False,
    ) -> LoadedMarketData:
        """Load from DB/cache or broker once; reuse cache for later reads in-process."""
        rows = self.load_candles(instrument, timeframe, start, end)
        if not force_fetch and self._rows_cover_window(rows, start, end, timeframe, min_ratio):
            self._release_db_transaction()
            return self._market_data_from_rows(rows, "database")

        # Broker fetch can take seconds; release the read lock before awaiting.
        self._release_db_transaction()
        try:
            api_candles = await fetch(start, end)
            self.store_candles(instrument, timeframe, api_candles)
            rows = self.load_candles(instrument, timeframe, start, end)
            if rows:
                return self._market_data_from_rows(rows, broker_label)
            cleaned = validate_candles(api_candles)
            return LoadedMarketData(
                candles=cleaned,
                price_series=[PriceBar(timestamp=c.timestamp, price=float(c.close)) for c in cleaned],
                source=broker_label,
            )
        except Exception as exc:
            if len(rows) >= 10:
                return self._market_data_from_rows(rows, "database (offline)")
            raise RuntimeError(
                f"{broker_label} API unavailable. Check network and {token_env}."
            ) from exc

    def has_sufficient_data(
        self,
        instrument: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        min_ratio: float = 0.5,
    ) -> bool:
        rows = self.load_candles(instrument, timeframe, start, end)
        return self._rows_cover_window(rows, start, end, timeframe, min_ratio)

    def close(self):
        self.session.close()

    @staticmethod
    def _market_data_from_rows(rows: list[CandleModel], source: str) -> LoadedMarketData:
        return LoadedMarketData(
            candles=[candle_model_to_engine(row) for row in rows],
            price_series=[candle_model_to_price_bar(row) for row in rows],
            source=source,
        )

    @staticmethod
    def _rows_cover_window(
        rows: list[CandleModel],
        start: datetime,
        end: datetime,
        timeframe: str,
        min_ratio: float,
    ) -> bool:
        if len(rows) < 10:
            return False
        bar_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
        span_seconds = (utc_naive(end) - utc_naive(start)).total_seconds()
        expected = max(span_seconds / bar_seconds, 1)
        return len(rows) >= expected * min_ratio
