"""DataLoader round-trip against SQLite."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_loader.loader import DataLoader, candle_model_to_engine
from src.db.models import CandleModel
from src.db.session import Base
from src.engine.models import Candle


@pytest.fixture
def loader(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr("src.data_loader.loader.SessionLocal", test_session)

    instance = DataLoader(use_cache=True)
    yield instance
    instance.close()


def _sample_candles(count: int = 3) -> list[Candle]:
    base = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return [
        Candle(
            timestamp=(base + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
            open=100.0 + i,
            high=101.0 + i,
            low=99.0 + i,
            close=100.5 + i,
            volume=1000.0 + i,
        )
        for i in range(count)
    ]


def test_store_and_load_engine_candles(loader: DataLoader):
    candles = _sample_candles()
    stored = loader.store_candles("SBER", "1h", candles)
    assert stored >= len(candles)

    start = datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    loaded = loader.load_engine_candles("SBER", "1h", start, end)

    assert len(loaded) == len(candles)
    assert loaded[0].timestamp == candles[0].timestamp
    assert loaded[-1].close == candles[-1].close


def test_upsert_updates_existing_row(loader: DataLoader):
    candle = _sample_candles(1)[0]
    loader.store_candles("SBER", "1h", [candle])

    updated = Candle(
        timestamp=candle.timestamp,
        open=200.0,
        high=201.0,
        low=199.0,
        close=200.5,
        volume=5000.0,
    )
    loader.store_candles("SBER", "1h", [updated])

    rows = loader.load_candles(
        "SBER",
        "1h",
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert float(rows[0].close) == pytest.approx(200.5)


def test_candle_model_to_engine():
    row = CandleModel(
        instrument="SBER",
        timeframe="1h",
        timestamp=datetime(2025, 6, 1, 12, 0, 0),
        open=250.0,
        high=251.0,
        low=249.0,
        close=250.5,
        volume=1234,
    )
    candle = candle_model_to_engine(row)
    assert candle.timestamp == "2025-06-01T12:00:00"
    assert candle.close == 250.5


def test_load_price_series(loader: DataLoader):
    candles = _sample_candles()
    loader.store_candles("SBER", "1h", candles)

    start = datetime(2025, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    end = datetime(2025, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    series = loader.load_price_series("SBER", "1h", start, end)

    assert len(series) == len(candles)
    assert series[0].timestamp == candles[0].timestamp
    assert series[-1].price == pytest.approx(candles[-1].close)


def test_load_candles_hits_in_memory_cache(loader: DataLoader, monkeypatch):
    candles = _sample_candles(50)
    loader.store_candles("SBER", "1h", candles)

    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = datetime(2025, 1, 3, tzinfo=timezone.utc)
    first_rows = loader.load_candles("SBER", "1h", start, end)

    def fail_db_query(*_args, **_kwargs):
        raise AssertionError("DB should not be queried when CandleCache is warm")

    monkeypatch.setattr(loader.session, "execute", fail_db_query)
    cached_rows = loader.load_candles("SBER", "1h", start, end)
    assert len(cached_rows) == len(first_rows)
    assert cached_rows[0].timestamp == first_rows[0].timestamp
