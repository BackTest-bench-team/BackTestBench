"""Market data is loaded once per bootstrap run; optimizer reuses in-memory candles."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import main
from src.db.session import Base
from src.engine.models import Candle


@pytest.fixture
def isolated_market_data(monkeypatch, tmp_path):
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


def test_shared_loader_reuses_data_without_second_broker_fetch(isolated_market_data):
    config, api_calls = isolated_market_data

    async def run():
        loader = main.DataLoader(use_cache=True)
        _, first = await main.load_market_data(config, loader=loader)
        _, second = await main.load_market_data(config, loader=loader)
        loader.close()
        return first, second

    first, second = asyncio.run(run())

    assert len(first.candles) == 400
    assert len(first.price_series) == 400
    assert first.source == "T-Bank"
    assert second.source == "database"
    assert api_calls["count"] == 1
    assert first.price_series[0].price == pytest.approx(100.5)
    assert second.candles[0].close == first.candles[0].close


def test_multiple_strategy_runs_use_single_market_load(isolated_market_data, monkeypatch):
    config, api_calls = isolated_market_data
    backtest_calls = {"count": 0}

    def fake_backtest(strategy_id, params, candles, cfg):
        backtest_calls["count"] += 1
        assert len(candles) == 400
        return {
            "strategy_id": strategy_id,
            "status": "completed",
            "params": params,
            "metrics": {},
            "chart_points": [],
            "trade_log": [],
            "final_portfolio": {},
            "error": None,
        }

    monkeypatch.setattr(main, "run_strategy_backtest", fake_backtest)
    monkeypatch.setattr(
        main,
        "runtime_strategies",
        lambda _cfg: [
            {"id": "ma_crossover", "params": {}},
            {"id": "rsi_threshold", "params": {}},
        ],
    )
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(main, "load_dashboard", main.default_dashboard)
    monkeypatch.setattr(main, "save_dashboard", lambda _data: None)
    monkeypatch.setattr(main, "write_run_pid", lambda: None)
    monkeypatch.setattr(main, "clear_run_pid", lambda: None)
    monkeypatch.setattr(main, "clear_stop_request", lambda: None)
    monkeypatch.setattr(main, "stop_requested", lambda: False)

    asyncio.run(main.bootstrap_all())

    assert api_calls["count"] == 1
    assert backtest_calls["count"] == 2
