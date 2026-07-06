"""
Bybit Broker Adapter implementation.

Implements the BrokerAdapter interface against Bybit's V5 public market-data
endpoint (``/v5/market/kline``). Candle data is **public** — the API key is not
required and is not sent with kline requests; it is accepted only for parity
with the other adapters and stored in case future functionality needs it.

API reference: https://bybit-exchange.github.io/docs/v5/market/kline

Key behaviour:
* The endpoint caps each request at **200 candles**, so a date range that
  spans more than 200 bars is fetched transparently via windowed pagination.
* The response is returned newest-first; we flip to oldest-first to match the
  chronological ordering expected by the engine/strategies (and the other
  adapters).
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

# Bybit V5 REST base URL.
BASE_URL = "https://api.bybit.com"

# Map the project-wide timeframe format (same as the T-Bank/Twelve Data
# adapters: "1m", "5m", "1h", "1d", ...) onto Bybit's internal interval names.
TIMEFRAME_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}

# Bybit caps each kline request at this many candles; we paginate around it.
_PAGE_SIZE = 200

# Bybit retCode values that signal an unknown symbol / unsupported interval.
_RET_INVALID_SYMBOL_OR_INTERVAL = 10001
# retCode for rate limiting on the public endpoints.
_RET_RATE_LIMITED = 10006


class BybitAdapter(BrokerAdapter):
    """Concrete implementation of BrokerAdapter for the Bybit V5 REST API."""

    def __init__(self, token: Optional[str] = None, category: str = "spot"):
        """
        Args:
            token: Optional API key. Read from ``BYBIT_TOKEN`` if not given.
                Candle data is public, so the key is **not** required and is
                not sent with kline requests.
            category: Bybit product category — ``"spot"`` (default),
                ``"linear"`` (USDT-margined perpetuals), or ``"inverse"``.
                Prices/volumes differ between categories for the same symbol.
        """
        # Public endpoint: token is optional. Read it for parity but never fail
        # if it is absent.
        self.token = token or os.getenv("BYBIT_TOKEN")
        self.category = category
        self._session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        """Open an HTTP session and verify basic connectivity.

        A single one-candle request confirms the host is reachable and the
        category/symbol shape is valid. Auth isn't exercised (the kline
        endpoint is public), so this never raises ``AuthenticationError``.
        """
        try:
            self._session = aiohttp.ClientSession()
            params = {
                "category": self.category,
                "symbol": "BTCUSDT",
                "interval": "D",
            }
            async with self._session.get(
                f"{BASE_URL}/v5/market/kline", params=params
            ) as resp:
                payload = await resp.json()
            if isinstance(payload, dict) and payload.get("retCode") not in (None, 0):
                raise BrokerError(
                    f"Bybit connectivity check failed: "
                    f"{payload.get('retCode')} {payload.get('retMsg', '')}"
                )
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
        """Retrieve historical candles from Bybit, paginating past the 200 cap.

        Args:
            instrument: Bybit symbol (e.g. ``"BTCUSDT"``, ``"ETHUSDT"``).
            timeframe: Project-wide timeframe (``"1m"``…``"1M"``).
            from_dt: Start datetime (inclusive).
            to_dt: End datetime (inclusive).
            limit: Optional cap on the total number of returned candles.
            offset: Unused by Bybit REST; accepted for interface parity.
        """
        if not self._session:
            raise BrokerError("Not connected.")

        interval = TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe: {timeframe!r}. "
                f"Supported values: {', '.join(TIMEFRAME_MAP)}."
            )

        # Bybit expects millisecond epoch timestamps.
        start_ms = int(from_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)
        end_ms = int(to_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

        rows: List[list] = []
        seen: set = set()
        cursor = start_ms

        # Windowed pagination: each request covers at most _PAGE_SIZE candles,
        # so for wide ranges (e.g. years of 1m bars) we advance `cursor` past
        # the last candle returned and repeat until we reach end_ms.
        while cursor <= end_ms:
            params = {
                "category": self.category,
                "symbol": instrument,
                "interval": interval,
                "start": str(cursor),
                "end": str(end_ms),
                "limit": str(_PAGE_SIZE),
            }
            async with self._session.get(
                f"{BASE_URL}/v5/market/kline", params=params
            ) as resp:
                payload = await resp.json()

            if isinstance(payload, dict) and payload.get("retCode") not in (None, 0):
                self._raise_for_retcodes(
                    payload.get("retCode"), payload.get("retMsg", ""), instrument
                )

            page = (payload.get("result") or {}).get("list") or []
            if not page:
                break

            # page is newest-first; append dedup'd rows in arrival order.
            new_rows = []
            for row in page:
                ts_ms = int(row[0])
                if ts_ms in seen:
                    continue
                seen.add(ts_ms)
                new_rows.append(row)
            rows.extend(new_rows)

            # Advance the cursor to just past the oldest candle in this page
            # (page is newest-first, so the last element is the oldest).
            oldest_ms = int(page[-1][0])
            if len(page) < _PAGE_SIZE:
                # Fewer than a full page means the window is exhausted.
                break
            # +1 ms to avoid re-fetching the boundary candle.
            cursor = oldest_ms + 1
            if oldest_ms >= end_ms:
                break

        # Newest-first -> oldest-first (chronological, as the engine expects).
        rows.sort(key=lambda r: int(r[0]))

        candles = [self._convert_candle(r) for r in rows]
        if limit:
            candles = candles[:limit]
        return candles

    def _raise_for_retcodes(self, ret_code, ret_msg: str, instrument: str) -> None:
        """Translate a Bybit retCode into the appropriate adapter exception."""
        if ret_code == _RET_INVALID_SYMBOL_OR_INTERVAL:
            raise InvalidInstrumentError(
                f"Bybit does not recognise symbol/interval "
                f"({instrument!r}): {ret_code} {ret_msg}"
            )
        if ret_code == _RET_RATE_LIMITED:
            raise RateLimitError(f"Bybit rate limit: {ret_code} {ret_msg}")
        if ret_code in (401, 403):
            raise AuthenticationError(f"Bybit auth error: {ret_code} {ret_msg}")
        raise BrokerError(f"Bybit error {ret_code}: {ret_msg}")

    def _convert_candle(self, row: list) -> Candle:
        """Convert a Bybit kline row into the unified Candle model.

        Row layout: ``[startTimeMs, open, high, low, close, volume, turnover]``.
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
