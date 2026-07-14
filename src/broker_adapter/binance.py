"""
Binance Broker Adapter implementation.

Implements the BrokerAdapter interface against Binance's public REST klines
endpoint (``/api/v3/klines``). Candle data is **public** — the API key is not
required and is not sent with kline requests; it is accepted only for parity
with the other adapters and stored in case future functionality (e.g. private
endpoints for trading/account) needs it.

API reference:
https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints

Key behaviour:
* The endpoint caps each request at **1000 candles**, so a date range that
  spans more than 1000 bars is fetched transparently via windowed pagination
  (forward from ``startTime``).
* The response is returned oldest-first (Binance's natural order), matching
  the chronological ordering expected by the engine/strategies (and the other
  adapters) — no reversal is needed.
* The unified ``Candle`` model from ``src.engine.models`` is reused, so
  downstream code is identical regardless of source.
"""

import os
from datetime import datetime, timezone
from typing import List, Optional

import aiohttp

from .base import (
    BrokerAdapter,
    BrokerError,
    AuthenticationError,
    InvalidInstrumentError,
    RateLimitError,
)
from .models import Candle

# Binance REST base URL (spot market data).
BASE_URL = "https://api.binance.com"

# Map the project-wide timeframe format (same as the T-Bank/Twelve Data/Bybit
# adapters: "1m", "5m", "1h", "1d", ...) onto Binance's kline interval names.
# Binance happens to use identical labels for the 8 supported values, so the
# mapping is identity — it is still spelled out for clarity and to make the
# supported set explicit (Binance also exposes 2h, 4h, 6h, 8h, 12h, 3d which
# the project does not surface).
TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
    "1M": "1M",
}

# Binance caps each kline request at this many candles; we paginate past it.
_PAGE_SIZE = 1000

# HTTP status codes returned by Binance for the corresponding error classes.
_HTTP_BAD_SYMBOL = 400      # Invalid symbol / interval -> {"code": -1121, ...}
_HTTP_RATE_LIMITED = 429    # Rate limit (Retry-After header included)
_HTTP_TOO_MANY_REQ = 418    # IP ban after repeated 429s
_HTTP_AUTH = 401            # Only relevant for private endpoints; klines are public.


class BinanceAdapter(BrokerAdapter):
    """Concrete implementation of BrokerAdapter for the Binance spot REST API."""

    def __init__(self, token: Optional[str] = None):
        """
        Args:
            token: Optional API key. Read from ``BINANCE_TOKEN`` if not given.
                Candle data is public, so the key is **not** required and is
                not sent with kline requests.
        """
        # Public endpoint: token is optional. Read it for parity but never fail
        # if it is absent.
        self.token = token or os.getenv("BINANCE_TOKEN")
        self._session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        """Open an HTTP session and verify basic connectivity.

        A single one-candle request confirms the host is reachable. Auth isn't
        exercised (the kline endpoint is public), so this never raises
        ``AuthenticationError``.
        """
        try:
            self._session = aiohttp.ClientSession()
            params = {
                "symbol": "BTCUSDT",
                "interval": "1d",
                "limit": 1,
            }
            async with self._session.get(
                f"{BASE_URL}/api/v3/klines", params=params
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise BrokerError(
                        f"Binance connectivity check failed: "
                        f"{resp.status} {body[:200]}"
                    )
                # Drain the body so the connection can be reused.
                await resp.read()
        except Exception:
            if self._session is not None:
                await self._session.close()
                self._session = None
            raise

    async def disconnect(self) -> None:
        """Close the underlying HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def get_candles(
        self,
        instrument: str,
        timeframe: str,
        from_dt: datetime,
        to_dt: datetime,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Candle]:
        """Retrieve historical candles from Binance, paginating past the 1000 cap.

        Args:
            instrument: Binance symbol (e.g. ``"BTCUSDT"``, ``"ETHBTC"``,
                ``"EURUSDT"`` — Binance lists a number of fiat-quoted
                stablecoin pairs that behave like FX).
            timeframe: Project-wide timeframe (``"1m"``…``"1M"``).
            from_dt: Start datetime (inclusive).
            to_dt: End datetime (inclusive).
            limit: Optional cap on the total number of returned candles.
            offset: Unused by Binance REST; accepted for interface parity.
        """
        if not self._session:
            raise BrokerError("Not connected.")

        interval = TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe: {timeframe!r}. "
                f"Supported values: {', '.join(TIMEFRAME_MAP)}."
            )

        # Binance expects millisecond epoch timestamps (UTC).
        start_ms = int(from_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(to_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

        rows: List[list] = []
        window_start = start_ms

        # Paginate forward from start_ms: each request returns up to _PAGE_SIZE
        # candles oldest-first; the next window starts just after the last
        # received candle's open time to avoid duplicates.
        while window_start <= end_ms:
            params = {
                "symbol": instrument,
                "interval": interval,
                "startTime": str(window_start),
                "endTime": str(end_ms),
                "limit": str(_PAGE_SIZE),
            }
            async with self._session.get(
                f"{BASE_URL}/api/v3/klines", params=params
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self._raise_for_status(resp.status, body, instrument)
                page = await resp.json()

            if not page:
                break

            last_open_ms = int(page[-1][0])
            rows.extend(page)

            # Stop if we received fewer than the page cap (no more history) or
            # the last candle's open time has reached/passed the requested end.
            if len(page) < _PAGE_SIZE or last_open_ms >= end_ms:
                break

            # Advance past the last received candle to avoid duplicates.
            next_start = last_open_ms + 1
            if next_start <= window_start:
                # Defensive: if the API ever returns a row with an open time
                # before our window_start, break to avoid an infinite loop.
                break
            window_start = next_start

        candles = [self._convert_candle(r) for r in rows]
        if limit:
            candles = candles[:limit]
        return candles

    def _raise_for_status(self, status: int, body: str, instrument: str) -> None:
        """Translate a Binance HTTP error into the appropriate adapter exception.

        Binance returns JSON error bodies like ``{"code": -1121, "msg": "Invalid
        symbol."}`` for known bad-symbol/interval combinations, but for the
        adapter we treat any 4xx with a symbol context as InvalidInstrumentError
        — the surface message is preserved in the exception text.
        """
        if status in (_HTTP_RATE_LIMITED, _HTTP_TOO_MANY_REQ):
            raise RateLimitError(f"Binance rate limit: {status} {body[:200]}")
        if status == _HTTP_AUTH:
            raise AuthenticationError(f"Binance auth error: {status} {body[:200]}")
        if status == _HTTP_BAD_SYMBOL:
            raise InvalidInstrumentError(
                f"Binance does not recognise symbol {instrument!r}: {body[:200]}"
            )
        raise BrokerError(f"Binance HTTP {status}: {body[:200]}")

    def _convert_candle(self, row: list) -> Candle:
        """Convert a Binance kline row into the unified Candle model.

        Row layout: ``[openTime, open, high, low, close, volume, closeTime,
        quoteAssetVolume, numberOfTrades, takerBuyBaseVolume,
        takerBuyQuoteVolume, ignore]``. Times are ms epoch (UTC).
        """
        ts_ms = int(row[0])
        timestamp_str = datetime.fromtimestamp(
            ts_ms / 1000, tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S")
        return Candle(
            timestamp=timestamp_str,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]) if len(row) > 5 and row[5] not in (None, "") else 0.0,
        )

    async def place_order(self, instrument, action, quantity, price=None):
        """Place order - not implemented."""
        raise NotImplementedError("Order placement not yet implemented")

    async def get_portfolio(self, account_id=None):
        """Get portfolio - not implemented."""
        raise NotImplementedError("Portfolio retrieval not yet implemented")
