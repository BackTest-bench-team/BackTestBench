"""Prove main.get_candles uses DataLoader: API once, then database."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from src.db.session import Base
from src.engine.models import Candle


@pytest.fixture
def isolated_candle_pipeline(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr("src.data_loader.loader.SessionLocal", session_factory)
    monkeypatch.setattr(main, "init_db", lambda: Base.metadata.create_all(bind=engine))

    api_calls = {"count": 0}

    async def fake_fetch(_config, from_dt, _to_dt):
        api_calls["count"] += 1
        base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return [
            Candle(
                timestamp=(base - timedelta(hours=399 - i)).strftime("%Y-%m-%dT%H:%M:%S"),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000.0,
            )
            for i in range(400)
        ]

    monkeypatch.setattr(main, "fetch_candles_from_api", fake_fetch)

    config = {"instrument": "SBER", "timeframe": "1h", "lookback_days": 30}
    return config, api_calls


def test_get_candles_uses_database_on_second_call(isolated_candle_pipeline):
    config, api_calls = isolated_candle_pipeline

    candles_first, source_first = asyncio.run(main.get_candles(config))
    candles_second, source_second = asyncio.run(main.get_candles(config))

    assert len(candles_first) == 400
    assert source_first == "T-Bank"
    assert api_calls["count"] == 1

    assert len(candles_second) == 400
    assert source_second == "database"
    assert api_calls["count"] == 1
