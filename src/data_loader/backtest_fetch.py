"""Chunked backtest candle loading: SQLite cache + sequential broker requests."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.broker_adapter.factory import source_display_name
from src.data_loader.loader import DataLoader, _TIMEFRAME_SECONDS, utc_naive
from src.db.session import init_db
from src.engine.models import Candle

_META_PATH = Path(__file__).resolve().parents[2] / "data" / "market-data-meta.json"

# Max bars per single broker request (slightly below adapter page caps).
_CHUNK_BARS_BY_SOURCE: dict[str, int] = {
    "binance": 900,
    "bybit": 180,
    "twelvedata": 4000,
    "tbank": 1440,
}

FetchFn = Callable[[dict[str, Any], datetime, datetime], Awaitable[list[Candle]]]
ProgressFn = Callable[[int, int], None]


def _load_meta() -> dict[str, str] | None:
    if not _META_PATH.exists():
        return None
    try:
        payload = json.loads(_META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return {
        "instrument": str(payload.get("instrument", "")),
        "timeframe": str(payload.get("timeframe", "")),
        "data_source": str(payload.get("data_source", "")),
    }


def _save_meta(config: dict[str, Any]) -> None:
    _META_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "instrument": config["instrument"],
        "timeframe": config["timeframe"],
        "data_source": config["data_source"],
    }
    _META_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _maybe_clear_on_timeframe_change(loader: DataLoader, config: dict[str, Any]) -> None:
    """Drop stored candles when the user switches timeframe on Run backtest."""
    meta = _load_meta()
    instrument = str(config["instrument"])
    timeframe = str(config["timeframe"])
    if meta is None:
        _save_meta(config)
        return
    if meta.get("instrument") == instrument and meta.get("timeframe") != timeframe:
        loader.clear_candles(instrument, str(meta["timeframe"]))
    _save_meta(config)


def _bar_tolerance(timeframe: str) -> timedelta:
    bar_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    return timedelta(seconds=bar_seconds * 2)


def coverage_gaps(
    earliest: datetime | None,
    latest: datetime | None,
    from_dt: datetime,
    to_dt: datetime,
    timeframe: str,
) -> list[tuple[datetime, datetime]]:
    """Return date ranges that still need broker fetch (empty = DB is enough)."""
    tolerance = _bar_tolerance(timeframe)
    if earliest is None or latest is None:
        return [(from_dt, to_dt)]

    gaps: list[tuple[datetime, datetime]] = []
    if utc_naive(earliest) > utc_naive(from_dt) + tolerance:
        gaps.append((from_dt, earliest - timedelta(seconds=1)))
    if utc_naive(latest) < utc_naive(to_dt) - tolerance:
        gaps.append((latest + timedelta(seconds=1), to_dt))
    return gaps


def chunk_windows(
    from_dt: datetime,
    to_dt: datetime,
    *,
    data_source: str,
    timeframe: str,
) -> list[tuple[datetime, datetime]]:
    """Split a gap into sequential windows sized for one broker page."""
    bar_seconds = _TIMEFRAME_SECONDS.get(timeframe, 3600)
    chunk_bars = _CHUNK_BARS_BY_SOURCE.get(data_source, 500)
    chunk_delta = timedelta(seconds=bar_seconds * chunk_bars)

    windows: list[tuple[datetime, datetime]] = []
    cursor = from_dt
    while utc_naive(cursor) < utc_naive(to_dt):
        end = min(cursor + chunk_delta, to_dt)
        windows.append((cursor, end))
        cursor = end + timedelta(seconds=1)
    return windows


async def _fetch_gaps(
    config: dict[str, Any],
    gaps: list[tuple[datetime, datetime]],
    fetch_fn: FetchFn,
    loader: DataLoader,
    on_progress: ProgressFn | None = None,
) -> int:
    """Fetch each gap in sequential chunks and persist to SQLite."""
    instrument = str(config["instrument"])
    timeframe = str(config["timeframe"])
    data_source = str(config.get("data_source", "tbank"))
    api_calls = 0

    windows: list[tuple[datetime, datetime]] = []
    for gap_from, gap_to in gaps:
        windows.extend(
            chunk_windows(gap_from, gap_to, data_source=data_source, timeframe=timeframe)
        )

    if not windows:
        if on_progress:
            on_progress(1, 1)
        return 0

    total = len(windows)
    if on_progress:
        on_progress(0, total)

    for index, (chunk_from, chunk_to) in enumerate(windows, start=1):
        candles = await fetch_fn(config, chunk_from, chunk_to)
        api_calls += 1
        if candles:
            loader.store_candles(instrument, timeframe, candles)
        loader._release_db_transaction()
        if on_progress:
            on_progress(index, total)

    return api_calls


async def ensure_backtest_candles(
    config: dict[str, Any],
    from_dt: datetime,
    to_dt: datetime,
    fetch_fn: FetchFn,
    on_progress: ProgressFn | None = None,
) -> tuple[list[Candle], str, int]:
    """Load candles for backtest: DB-first, broker only for missing ranges.

    Returns (candles, source_label, api_call_count).
    """
    init_db()
    instrument = str(config["instrument"])
    timeframe = str(config["timeframe"])
    broker_label = source_display_name(str(config.get("data_source", "tbank")))

    loader = DataLoader(use_cache=False)
    try:
        _maybe_clear_on_timeframe_change(loader, config)
        earliest, latest = loader.get_candle_bounds(instrument, timeframe)
        gaps = coverage_gaps(earliest, latest, from_dt, to_dt, timeframe)

        api_calls = 0
        if gaps:
            api_calls = await _fetch_gaps(config, gaps, fetch_fn, loader, on_progress=on_progress)
        elif on_progress:
            on_progress(1, 1)

        candles = loader.load_engine_candles(instrument, timeframe, from_dt, to_dt)
        if not candles:
            raise RuntimeError("No candles available for backtest window")

        source = "database" if api_calls == 0 else broker_label
        return candles, source, api_calls
    finally:
        loader.close()
