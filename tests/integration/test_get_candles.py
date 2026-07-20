"""Prove main.get_candles uses DB cache on repeated calls with same settings."""
import asyncio
from datetime import datetime, timedelta, timezone

import main
from src.engine.models import Candle
from tests.integration.db_helpers import patch_isolated_candle_db


def test_get_candles_uses_db_cache_on_second_call(monkeypatch, tmp_path):
    api_calls = {"count": 0}

    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)

    async def fake_fetch(_config, from_dt, to_dt):
        api_calls["count"] += 1
        span_hours = max(1, int((to_dt - from_dt).total_seconds() // 3600) + 1)
        return [
            Candle(
                timestamp=(from_dt + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%S"),
                open=100.0 + i,
                high=101.0 + i,
                low=99.0 + i,
                close=100.5 + i,
                volume=1000.0,
            )
            for i in range(span_hours)
        ]

    monkeypatch.setattr(main, "fetch_candles_from_api", fake_fetch)
    monkeypatch.setattr(
        "src.data_loader.backtest_fetch._META_PATH",
        tmp_path / "meta.json",
    )
    patch_isolated_candle_db(monkeypatch, tmp_path / "backtest.db")

    base = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    config = {
        "instrument": "SBER",
        "timeframe": "1h",
        "lookback_days": 30,
        "data_source": "tbank",
        "period_end": base.isoformat(),
    }
    candles_first, source_first = asyncio.run(main.get_candles(config))
    candles_second, source_second = asyncio.run(main.get_candles(config))

    expected = 30 * 24 + 1
    assert len(candles_first) == expected
    assert source_first == "T-Bank"
    assert len(candles_second) == expected
    assert source_second == "database"
    assert api_calls["count"] == 1
