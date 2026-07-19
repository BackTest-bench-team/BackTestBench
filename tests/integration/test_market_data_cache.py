"""Market data is loaded once per bootstrap run; strategies reuse in-memory candles."""
import asyncio
from datetime import datetime, timedelta, timezone

import main
from src.engine.models import Candle
from tests.integration.db_helpers import patch_isolated_candle_db


def test_bootstrap_uses_single_broker_fetch(monkeypatch, tmp_path):
    api_calls = {"count": 0}

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

    backtest_calls = {"count": 0}
    expected_bars = 30 * 24 + 1

    def fake_backtest(strategy_id, params, candles, cfg):
        backtest_calls["count"] += 1
        assert len(candles) == expected_bars
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

    config = {
        "instrument": "SBER",
        "timeframe": "1h",
        "lookback_days": 30,
        "data_source": "tbank",
        "period_end": datetime.now(timezone.utc)
        .replace(minute=0, second=0, microsecond=0)
        .isoformat(),
    }
    monkeypatch.setattr(main, "fetch_candles_from_api", fake_fetch)
    monkeypatch.setattr(
        "src.data_loader.backtest_fetch._META_PATH",
        tmp_path / "meta.json",
    )
    patch_isolated_candle_db(monkeypatch, tmp_path / "backtest.db")
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
