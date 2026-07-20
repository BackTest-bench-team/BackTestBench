import asyncio
import json

import main
import pytest


def test_live_run_start_and_stop_exclusive(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "LIVE_RUN_FILE", tmp_path / "live-run.json")
    monkeypatch.setattr(main, "LIVE_TICK_LOCK_FILE", tmp_path / "live-run.tick.lock")
    monkeypatch.setattr(main, "PID_FILE", tmp_path / "backtest.pid")
    monkeypatch.setattr(main, "is_backtest_running", lambda: False)

    async def fake_tick(*, force=False):
        return {"ok": True, "active": True, "strategy": {"strategy_id": "alpha"}, "live": {}}

    monkeypatch.setattr(main, "live_run_tick_command", fake_tick)

    started = asyncio.run(
        main.live_run_start_command(
            json.dumps({"strategy_id": "alpha", "params": {"fast": 5, "slow": 20, "order_size": 1}})
        )
    )
    assert started["ok"] is True
    assert started["active"] is True

    with pytest.raises(RuntimeError, match="already live"):
        asyncio.run(
            main.live_run_start_command(
                json.dumps({"strategy_id": "beta", "params": {"fast": 5, "slow": 20, "order_size": 1}})
            )
        )

    stopped = main.live_run_stop_command(json.dumps({"strategy_id": "alpha"}))
    assert stopped["active"] is False
    assert main.load_live_run() is None


def test_live_run_status_clears_when_backtest_running(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "LIVE_RUN_FILE", tmp_path / "live-run.json")
    monkeypatch.setattr(main, "LIVE_TICK_LOCK_FILE", tmp_path / "live-run.tick.lock")
    monkeypatch.setattr(main, "BACKTEST_PENDING_FILE", tmp_path / "backtest.pending")
    main.save_live_run({"strategy_id": "alpha", "params": {}, "started_at": "2026-01-01T00:00:00+00:00"})
    monkeypatch.setattr(main, "is_backtest_active", lambda: True)
    monkeypatch.setattr(main, "DASHBOARD_FILE", tmp_path / "runtime-dashboard.json")

    payload = main.live_run_status_command()
    assert payload["active"] is False
    assert payload["stopped_reason"] == "backtest_started"
    assert main.load_live_run() is None


def test_prepare_bootstrap_clears_live_and_marks_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "DATA_DIR", tmp_path)
    monkeypatch.setattr(main, "LIVE_RUN_FILE", tmp_path / "live-run.json")
    monkeypatch.setattr(main, "BACKTEST_PENDING_FILE", tmp_path / "backtest.pending")
    main.save_live_run({"strategy_id": "alpha", "params": {}, "started_at": "2026-01-01T00:00:00+00:00"})

    result = main.prepare_bootstrap_command()
    assert result["ok"] is True
    assert main.load_live_run() is None
    assert main.BACKTEST_PENDING_FILE.exists()
