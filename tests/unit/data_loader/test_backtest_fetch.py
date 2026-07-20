"""Tests for chunked backtest candle loading and cache policy."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data_loader.backtest_fetch import (
    _maybe_clear_on_timeframe_change,
    chunk_windows,
    coverage_gaps,
    ensure_backtest_candles,
)
from src.data_loader.loader import DataLoader
from src.db.models import CandleModel
from src.db.session import Base
from src.engine.models import Candle


@pytest.fixture
def loader_setup(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    test_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    monkeypatch.setattr("src.data_loader.loader.SessionLocal", test_session)

    meta_path = tmp_path / "meta.json"
    monkeypatch.setattr("src.data_loader.backtest_fetch._META_PATH", meta_path)

    loader = DataLoader(use_cache=False)
    yield loader, meta_path
    loader.close()


def _candle_at(base: datetime, i: int) -> Candle:
    ts = base + timedelta(hours=i)
    return Candle(
        timestamp=ts.strftime("%Y-%m-%dT%H:%M:%S"),
        open=100.0 + i,
        high=101.0 + i,
        low=99.0 + i,
        close=100.5 + i,
        volume=1000.0,
    )


def test_coverage_gaps_empty_when_db_covers_window():
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 10, tzinfo=timezone.utc)
    earliest = datetime(2025, 1, 1, tzinfo=timezone.utc)
    latest = datetime(2025, 1, 10, tzinfo=timezone.utc)
    assert coverage_gaps(earliest, latest, from_dt, to_dt, "1h") == []


def test_coverage_gaps_detects_early_and_late_missing():
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 10, tzinfo=timezone.utc)
    earliest = datetime(2025, 1, 3, tzinfo=timezone.utc)
    latest = datetime(2025, 1, 8, tzinfo=timezone.utc)
    gaps = coverage_gaps(earliest, latest, from_dt, to_dt, "1h")
    assert len(gaps) == 2
    assert gaps[0][0] == from_dt
    assert gaps[1][1] == to_dt


def test_coverage_gaps_full_window_when_db_empty():
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 5, tzinfo=timezone.utc)
    gaps = coverage_gaps(None, None, from_dt, to_dt, "1h")
    assert gaps == [(from_dt, to_dt)]


def test_chunk_windows_splits_long_range():
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 10, tzinfo=timezone.utc)
    windows = chunk_windows(from_dt, to_dt, data_source="bybit", timeframe="1h")
    assert len(windows) >= 2
    assert windows[0][0] == from_dt
    assert windows[-1][1] == to_dt


def test_clear_on_timeframe_change(loader_setup):
    loader, meta_path = loader_setup
    config = {"instrument": "SBER", "timeframe": "1h", "data_source": "tbank"}
    base = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    loader.store_candles("SBER", "1m", [_candle_at(base, 0)])
    loader.store_candles("SBER", "1h", [_candle_at(base, 1)])

    meta_path.write_text(
        '{"instrument":"SBER","timeframe":"1m","data_source":"tbank"}',
        encoding="utf-8",
    )
    _maybe_clear_on_timeframe_change(loader, config)

    assert loader.count_candles("SBER", "1m", base, base + timedelta(days=1)) == 0
    assert loader.count_candles("SBER", "1h", base, base + timedelta(days=1)) == 1


def test_ensure_backtest_candles_skips_api_when_db_covers(loader_setup, monkeypatch):
    import asyncio

    loader, _meta_path = loader_setup
    monkeypatch.setattr("src.data_loader.backtest_fetch.init_db", lambda: None)

    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = [_candle_at(base, i) for i in range(24)]
    loader.store_candles("SBER", "1h", candles)

    config = {
        "instrument": "SBER",
        "timeframe": "1h",
        "data_source": "tbank",
        "lookback_days": 1,
    }
    from_dt = base
    to_dt = base + timedelta(hours=23)

    async def run():
        async def fail_fetch(*_args, **_kwargs):
            raise AssertionError("broker should not be called when DB covers window")

        loaded, source, api_calls = await ensure_backtest_candles(
            config, from_dt, to_dt, fail_fetch
        )
        assert api_calls == 0
        assert source == "database"
        assert len(loaded) == 24

    asyncio.run(run())


def test_ensure_backtest_candles_fetches_only_early_gap(loader_setup, monkeypatch):
    import asyncio

    loader, _meta_path = loader_setup
    monkeypatch.setattr("src.data_loader.backtest_fetch.init_db", lambda: None)

    base = datetime(2025, 1, 5, 0, 0, 0, tzinfo=timezone.utc)
    loader.store_candles("SBER", "1h", [_candle_at(base, i) for i in range(24)])

    config = {
        "instrument": "SBER",
        "timeframe": "1h",
        "data_source": "tbank",
    }
    from_dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 5, 23, tzinfo=timezone.utc)
    fetched_ranges: list[tuple[datetime, datetime]] = []

    async def run():
        async def fake_fetch(_config, chunk_from, chunk_to):
            fetched_ranges.append((chunk_from, chunk_to))
            if chunk_from < base:
                return [_candle_at(chunk_from, i) for i in range(24)]
            return []

        loaded, source, api_calls = await ensure_backtest_candles(
            config, from_dt, to_dt, fake_fetch
        )
        assert api_calls >= 1
        assert all(r[1] < base for r in fetched_ranges)
        assert len(loaded) >= 24
        assert source != "database"

    asyncio.run(run())


def test_ensure_backtest_candles_decreased_lookback_uses_db_only(loader_setup, monkeypatch):
    import asyncio

    loader, _meta_path = loader_setup
    monkeypatch.setattr("src.data_loader.backtest_fetch.init_db", lambda: None)

    base = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    loader.store_candles("SBER", "1h", [_candle_at(base, i) for i in range(72)])

    config = {
        "instrument": "SBER",
        "timeframe": "1h",
        "data_source": "tbank",
    }
    from_dt = datetime(2025, 1, 2, tzinfo=timezone.utc)
    to_dt = datetime(2025, 1, 3, 23, tzinfo=timezone.utc)

    async def run():
        async def fail_fetch(*_args, **_kwargs):
            raise AssertionError("broker should not be called when lookback shrinks")

        loaded, source, api_calls = await ensure_backtest_candles(
            config, from_dt, to_dt, fail_fetch
        )
        assert api_calls == 0
        assert source == "database"
        assert 40 <= len(loaded) <= 50

    asyncio.run(run())
