"""
Broker Adapter - Simple API for fetching real market data from multiple sources.

This example supports four data providers:

* ``tbank``      — T-Bank (Tinkoff Investments) Invest API v2 (Russian market,
                   tickers like SBER/GAZP/LKOH). Token env var: ``TINKOFF_TOKEN``.
* ``twelvedata`` — Twelve Data (twelvedata.com) REST API (global equities, FX,
                   crypto; tickers like AAPL/MSFT/ETH/BTC). Token env var:
                   ``TWELVEDATA_TOKEN``.
* ``bybit``      — Bybit V5 public kline API (crypto spot pairs like
                   BTCUSDT/ETHUSDT). Token env var: ``BYBIT_TOKEN`` (**optional**
                   — the kline endpoint is public).
* ``binance``    — Binance public kline API (crypto spot pairs like BTCUSDT /
                   ETHBTC, plus fiat-quoted stablecoin pairs like EURUSDT).
                   Token env var: ``BINANCE_TOKEN`` (**optional** — the kline
                   endpoint is public).

The source is chosen either per-call via ``source=...`` or globally through the
``DATA_SOURCE`` env var (defaults to ``tbank``). All adapters return the same
unified ``Candle`` model, so the downstream parsing/backtest path is identical.

Usage:
    from examples.tbank_adapter_usage import fetch_candles, run_backtest

    # Fetch candles (source defaults to DATA_SOURCE / tbank)
    candles = asyncio.run(fetch_candles(
        instrument="SBER",
        timeframe="1h",
        days=30,
    ))

    # Pick the API explicitly
    candles = asyncio.run(fetch_candles(
        instrument="AAPL",
        source="twelvedata",
        timeframe="1h",
        days=30,
    ))

    # Or run full backtest
    result = run_backtest(
        instrument="SBER",
        timeframe="1h",
        days=30,
        initial_capital=100000,
        strategy_params={"fast": 10, "slow": 30, "order_size": 1.0},
    )

Tokens are read from environment variables (e.g. GitHub repository secrets in CI/CD).
The repository ``.env`` is loaded automatically on import via
``src.env_file.load_env_file_into_process`` — so the example is self-contained
and does not require running through ``python main.py`` to populate ``os.environ``.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the repository .env into os.environ on import, so get_token()/os.getenv()
# can see tokens the user placed in .env without having to run via main.py.
# This mirrors the README's promise that ".env is loaded automatically on import".
# Safe no-op if .env does not exist. Idempotent: existing os.environ values win.
from src.env_file import load_env_file_into_process

load_env_file_into_process()

from src.broker_adapter import (
    TBankAdapter,
    TwelveDataAdapter,
    BybitAdapter,
    BinanceAdapter,
)
from src.engine.models import Candle

# Supported timeframes (minimum resolution is 1 minute).
# Ordered from shortest to longest; each maps to a candle interval on every
# supported provider.
TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M")
MIN_TIMEFRAME = "1m"

# Supported data sources and the default used when `source` is not given.
# The default can be overridden via the DATA_SOURCE environment variable.
SUPPORTED_SOURCES = ("tbank", "twelvedata", "bybit", "binance")
DEFAULT_SOURCE = os.getenv("DATA_SOURCE", "tbank").strip().lower() or "tbank"

# Per-source token env-var names. For "bybit" and "binance" the token is
# optional (the kline endpoint is public), so a missing token does not raise.
TOKEN_ENV_BY_SOURCE = {
    "tbank": "TINKOFF_TOKEN",
    "twelvedata": "TWELVEDATA_TOKEN",
    "bybit": "BYBIT_TOKEN",
    "binance": "BINANCE_TOKEN",
}
# Sources whose API token is optional for fetching candles.
_OPTIONAL_TOKEN_SOURCES = frozenset({"bybit", "binance"})

# T-Bank sandbox limits how many days of history it serves per timeframe —
# wider ranges return empty. These caps apply only to source="tbank".
DAYS_LIMIT_BY_TIMEFRAME = {
    "1m": 1,
    "5m": 7,
    "15m": 24,
    "30m": 25,
    "1h": 100,
    "1d": 2400,
    "1w": 2100,
    "1M": 3600,
}

# Twelve Data does not share T-Bank's sandbox restriction, so we only apply a
# generous sanity ceiling to guard against pathological requests. The same soft
# cap applies to Bybit and Binance (their kline endpoints paginate past their
# per-request candle limit transparently, so there is no per-timeframe cap
# either).
_MAX_DAYS_TWELVEDATA = 3650
_MAX_DAYS_BYBIT = 3650
_MAX_DAYS_BINANCE = 3650


def _resolve_source(source: Optional[str]) -> str:
    """
    Normalize and validate the requested data source.

    Falls back to ``DEFAULT_SOURCE`` (i.e. the ``DATA_SOURCE`` env var, or
    ``tbank``) when ``source`` is ``None``.

    Raises:
        ValueError: If ``source`` is not one of the supported values.
    """
    resolved = (source or DEFAULT_SOURCE).strip().lower()
    if resolved not in SUPPORTED_SOURCES:
        raise ValueError(
            f"Unsupported source {source!r}. "
            f"Supported values: {', '.join(SUPPORTED_SOURCES)}."
        )
    return resolved


def _validate_timeframe(timeframe: str) -> str:
    """
    Validate the timeframe requested by the user.

    The minimum supported resolution is 1 minute ("1m"). Sub-minute values
    such as "1s" or "30s" are rejected with a clear error because none of the
    supported providers expose OHLC candles at finer granularities.

    Args:
        timeframe: Timeframe string provided by the caller.

    Returns:
        The validated timeframe string.

    Raises:
        ValueError: If the timeframe is not supported or finer than 1m.
    """
    if not isinstance(timeframe, str) or not timeframe:
        raise ValueError(
            f"timeframe must be a non-empty string, got: {timeframe!r}"
        )

    normalized = timeframe.strip()

    # Reject sub-minute intervals explicitly (e.g. "1s", "30s", "15s").
    if normalized.endswith("s"):
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}: the minimum supported "
            f"resolution is '{MIN_TIMEFRAME}' (1 minute). Sub-minute "
            f"intervals are not available from the supported data sources."
        )

    if normalized not in TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe {timeframe!r}. Supported values are: "
            f"{', '.join(TIMEFRAMES)}. The minimum resolution is '{MIN_TIMEFRAME}'."
        )

    return normalized


def _validate_days(source: str, timeframe: str, days: int) -> int:
    """
    Validate that the requested history depth (`days`) is acceptable for the
    given source and timeframe.

    * For ``tbank`` the sandbox only serves a bounded number of days per
      timeframe (see ``DAYS_LIMIT_BY_TIMEFRAME``); wider ranges return empty.
    * For ``twelvedata``, ``bybit`` and ``binance`` there is no per-timeframe
      sandbox cap, only a sanity ceiling (``_MAX_DAYS_TWELVEDATA`` /
      ``_MAX_DAYS_BYBIT`` / ``_MAX_DAYS_BINANCE``). They paginate past their
      per-request candle limit transparently.

    Args:
        source: Already-resolved data source ("tbank"/"twelvedata"/"bybit"/"binance").
        timeframe: Already-validated timeframe string.
        days: Number of days of history requested.

    Returns:
        The validated `days` value.

    Raises:
        ValueError: If `days` is not a positive integer or exceeds the cap.
    """
    if not isinstance(days, int) or isinstance(days, bool):
        raise ValueError(
            f"days must be a positive integer, got: {days!r}"
        )
    if days <= 0:
        raise ValueError(f"days must be a positive integer, got: {days}.")

    if source == "tbank":
        limit = DAYS_LIMIT_BY_TIMEFRAME[timeframe]
        if days > limit:
            raise ValueError(
                f"days={days} is too large for timeframe '{timeframe}'. "
                f"The T-Bank sandbox serves at most {limit} days for this "
                f"timeframe (wider ranges return no data). Lower the `days` "
                f"parameter or use a coarser timeframe. "
                f"Limits: {DAYS_LIMIT_BY_TIMEFRAME}."
            )
    elif source == "twelvedata":
        if days > _MAX_DAYS_TWELVEDATA:
            raise ValueError(
                f"days={days} is too large (max {_MAX_DAYS_TWELVEDATA})."
            )
    elif source == "bybit":
        if days > _MAX_DAYS_BYBIT:
            raise ValueError(
                f"days={days} is too large (max {_MAX_DAYS_BYBIT})."
            )
    else:  # binance
        if days > _MAX_DAYS_BINANCE:
            raise ValueError(
                f"days={days} is too large (max {_MAX_DAYS_BINANCE})."
            )
    return days


def get_token(source: str = DEFAULT_SOURCE) -> Optional[str]:
    """
    Load the API token for the given source from the environment.

    Args:
        source: Data source ("tbank"/"twelvedata"/"bybit"/"binance").

    Returns:
        The token read from the matching env var, or ``None`` for sources whose
        token is optional (e.g. ``bybit``/``binance``) when it is not set.

    Raises:
        ValueError: If the token is not set and is required for this source.
    """
    source = _resolve_source(source)
    env_var = TOKEN_ENV_BY_SOURCE[source]
    token = os.getenv(env_var)
    if not token:
        if source in _OPTIONAL_TOKEN_SOURCES:
            return None
        raise ValueError(
            f"{env_var} is not set. Configure it as an environment variable "
            f"(e.g. GitHub repository secret in CI/CD)."
        )
    return token


def _build_adapter(source: str, token: Optional[str] = None, **kwargs) -> Any:
    """
    Construct the broker adapter for the requested source.

    Args:
        source: Data source ("tbank"/"twelvedata"/"bybit"/"binance").
        token: API token. If None, loaded via :func:`get_token`.
        **kwargs: Source-specific options forwarded to the adapter
            constructor (e.g. ``use_sandbox`` for T-Bank).

    Returns:
        An instance of the appropriate BrokerAdapter subclass.
    """
    source = _resolve_source(source)
    if token is None:
        token = get_token(source)

    if source == "tbank":
        return TBankAdapter(token=token, verify_ssl=False, **kwargs)
    if source == "bybit":
        return BybitAdapter(token=token)
    if source == "binance":
        return BinanceAdapter(token=token)
    return TwelveDataAdapter(token=token)


async def fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> List[Candle]:
    """
    Fetch real historical candles from the selected data API.

    Args:
        instrument: Ticker symbol. T-Bank: "SBER", "GAZP", "LKOH".
            Twelve Data: "AAPL", "MSFT", "ETH/BTC".
            Bybit / Binance: "BTCUSDT", "ETHUSDT", "ETHBTC", "EURUSDT".
        timeframe: Candle timeframe ("1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M").
            Minimum resolution is "1m" — sub-minute intervals ("1s", "30s", ...) are
            rejected. Validated before any network call. The same format is used for
            every source.
        days: Number of days of history (default: 7). For source="tbank" this is
            capped per timeframe — see DAYS_LIMIT_BY_TIMEFRAME (e.g. 1m<=1, 1h<=100).
            Validated up front; too large a value raises ValueError instead of an
            empty API response.
        source: Data API to use: "tbank", "twelvedata", "bybit" or "binance".
            Defaults to the DATA_SOURCE env var, then "tbank".
        from_date: Start date in format "YYYY-MM-DD" (optional, overrides days)
        to_date: End date in format "YYYY-MM-DD" (optional, defaults to now)
        use_sandbox: Use T-Bank sandbox environment (ignored by other sources)
        token: API token (optional, reads from environment if not provided)

    Returns:
        List of Candle objects with real market data

    Raises:
        ValueError: On an unsupported timeframe/source or a `days` value larger
            than the source allows for that timeframe.
    """
    source = _resolve_source(source)

    # Validate inputs before any network call.
    timeframe = _validate_timeframe(timeframe)
    _validate_days(source, timeframe, days)

    if to_date:
        to_dt = datetime.strptime(to_date, "%Y-%m-%d")
    else:
        to_dt = datetime.now()

    if from_date:
        from_dt = datetime.strptime(from_date, "%Y-%m-%d")
    else:
        from_dt = to_dt - timedelta(days=days)

    adapter = _build_adapter(
        source,
        token=token,
        **({"use_sandbox": use_sandbox} if source == "tbank" else {}),
    )

    async with adapter:
        candles = await adapter.get_candles(
            instrument=instrument,
            timeframe=timeframe,
            from_dt=from_dt,
            to_dt=to_dt,
        )

    return candles


def run_fetch_candles(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 7,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> List[Candle]:
    """Synchronous wrapper for fetch_candles."""
    return asyncio.run(fetch_candles(
        instrument=instrument,
        timeframe=timeframe,
        days=days,
        source=source,
        from_date=from_date,
        to_date=to_date,
        use_sandbox=use_sandbox,
        token=token,
    ))


def run_backtest(
    instrument: str = "SBER",
    timeframe: str = "1h",
    days: int = 30,
    initial_capital: float = 100000.0,
    strategy_params: Optional[Dict[str, Any]] = None,
    source: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    use_sandbox: bool = False,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch candles and run backtest with MA Crossover strategy.

    Args:
        instrument: Ticker symbol (e.g. "SBER", "AAPL", "BTCUSDT")
        timeframe: Candle timeframe ("1h", "1d", etc.)
        days: Number of days of history
        initial_capital: Starting capital for backtest
        strategy_params: Strategy parameters (default: fast=10, slow=30, order_size=1.0)
        source: Data API to use: "tbank", "twelvedata", "bybit" or "binance".
            Defaults to the DATA_SOURCE env var, then "tbank".
        from_date: Start date "YYYY-MM-DD" (optional)
        to_date: End date "YYYY-MM-DD" (optional)
        use_sandbox: Use T-Bank sandbox environment (ignored by other sources)
        token: API token (optional, reads from environment if not provided)

    Returns:
        Dict with "trade_log", "final_portfolio", "candles_count"
    """
    from src.engine.execution_engine import ExecutionEngine
    from src.strategy.strategies.ma_crossover import MACrossover

    # Fetch candles
    candles = run_fetch_candles(
        instrument=instrument,
        timeframe=timeframe,
        days=days,
        source=source,
        from_date=from_date,
        to_date=to_date,
        use_sandbox=use_sandbox,
        token=token,
    )

    if not candles:
        return {"trade_log": [], "final_portfolio": None, "candles_count": 0}

    # Default strategy params
    if strategy_params is None:
        strategy_params = {"fast": 10, "slow": 30, "order_size": 1.0}

    # Create strategy and engine
    strategy = MACrossover(params=strategy_params)
    engine = ExecutionEngine()

    # Run backtest
    result = engine.run(
        strategy=strategy,
        candles=candles,
        initial_capital=initial_capital,
    )

    result["candles_count"] = len(candles)
    return result


if __name__ == "__main__":
    # The source can be set per-call via source=..., or globally through the
    # DATA_SOURCE environment variable. Here we run every provider to show
    # that the call surface is identical regardless of the data source.
    print(f"Default data source: {DEFAULT_SOURCE!r} "
          f"(override with DATA_SOURCE env var or source=... per call)\n")

    # ------------------------------------------------------------------
    # T-Bank (Tinkoff Investments) — Russian equities (SBER, GAZP, ...).
    # Requires TINKOFF_TOKEN in the environment.
    # ------------------------------------------------------------------
    print("Example 1: T-Bank — fetch weekly candles")
    try:
        candles = run_fetch_candles(
            instrument="SBER",
            source="tbank",
            timeframe="1w",
            days=365,
        )
        print(f"Fetched {len(candles)} candles")
        for c in candles[:5]:
            print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} "
                  f"C={c.close} V={c.volume}")
    except Exception as e:  # noqa: BLE001 — keep the demo running across sources
        print(f"  skipped ({type(e).__name__}: {e})")

    print()

    # ------------------------------------------------------------------
    # Twelve Data — global equities / FX / crypto (AAPL, MSFT, ETH/BTC, ...).
    # Requires TWELVEDATA_TOKEN in the environment.
    # ------------------------------------------------------------------
    print("Example 2: Twelve Data — fetch daily candles")
    try:
        candles = run_fetch_candles(
            instrument="ETH",
            source="twelvedata",
            timeframe="1m",
            days=1,
        )
        print(f"Fetched {len(candles)} candles")
        for c in candles[:5]:
            print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} "
                  f"C={c.close} V={c.volume}")
    except Exception as e:  # noqa: BLE001
        print(f"  skipped ({type(e).__name__}: {e})")

    print()

    # ------------------------------------------------------------------
    # Bybit — crypto spot pairs (BTCUSDT, ETHUSDT, ...). No token required
    # ------------------------------------------------------------------
    print("Example 3: Bybit — fetch daily candles (TKXUSDT spot)")
    try:
        candles = run_fetch_candles(
            instrument="BTCUSDT",
            source="bybit",
            timeframe="1d",
            days=60,
        )
        print(f"Fetched {len(candles)} candles")
        for c in candles[:5]:
            print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} "
                  f"C={c.close} V={c.volume}")
    except Exception as e:  # noqa: BLE001
        print(f"  skipped ({type(e).__name__}: {e})")

    print()

    # ------------------------------------------------------------------
    # Binance — crypto spot pairs (BTCUSDT, ETHBTC, EURUSDT, ...).
    # No token required (the kline endpoint is public).
    # ------------------------------------------------------------------
    print("Example 4: Binance — fetch daily candles for BTCUSDT")
    try:
        candles = run_fetch_candles(
            instrument="BTCUSDT",
            source="binance",
            timeframe="1m",
            days=3650,
        )
        print(f"Fetched {len(candles)} candles")
        for c in candles[:5]:
            print(f"  {c.timestamp}: O={c.open} H={c.high} L={c.low} "
                  f"C={c.close} V={c.volume}")
    except Exception as e:  # noqa: BLE001
        print(f"  skipped ({type(e).__name__}: {e})")

    print()

    # ------------------------------------------------------------------
    # Full backtest — uses DEFAULT_SOURCE (DATA_SOURCE / tbank).
    # ------------------------------------------------------------------
    print(f"Example 5: Full backtest (source={DEFAULT_SOURCE!r})")
    try:
        result = run_backtest(
            instrument="SBER",
            timeframe="1M",
            days=40,
            initial_capital=100000,
            strategy_params={"fast": 10, "slow": 30, "order_size": 1.0},
        )
        print(f"Candles: {result['candles_count']}")
        print(f"Trades: {len(result['trade_log'])}")
        for trade in result['trade_log'][:5]:
            print(f"  {trade.timestamp}: PnL={trade.pnl:+.2f}")
        if result['final_portfolio']:
            print(f"Final equity: {result['final_portfolio'].equity:.2f}")
    except Exception as e:  # noqa: BLE001
        print(f"  skipped ({type(e).__name__}: {e})")
