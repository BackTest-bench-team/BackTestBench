"""
Twelve Data (twelvedata.com) Broker Adapter implementation.

This module implements the BrokerAdapter interface using the Twelve Data
REST API for historical OHLC candles. It reuses the unified ``Candle``
model from ``src.engine.models`` so downstream code (engine, strategies,
examples) works identically regardless of the data source.

API reference: https://twelvedata.com/docs#time-series
"""

import os
from datetime import datetime
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

# Twelve Data base URL for the REST API.
BASE_URL = "https://api.twelvedata.com"

# Map the project-wide timeframe format (same as the T-Bank adapter:
# "1m", "5m", "1h", "1d", ...) onto Twelve Data's internal interval names.
TIMEFRAME_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "1d": "1day",
    "1w": "1week",
    "1M": "1month",
}

# Twelve Data timestamp formats used in /time_series responses:
# * intraday intervals -> "YYYY-MM-DD HH:MM:SS"
# * daily/weekly/monthly -> "YYYY-MM-DD" (no time component)
_TS_PARSE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d")
_TS_DUMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_timestamp(raw: str) -> datetime:
    """Parse a Twelve Data timestamp, accepting both date-only and datetime forms."""
    for fmt in _TS_PARSE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Could not parse Twelve Data timestamp {raw!r}. "
        f"Expected one of: {', '.join(_TS_PARSE_FORMATS)}."
    )


class TwelveDataAdapter(BrokerAdapter):
    """Concrete implementation of BrokerAdapter for the Twelve Data REST API."""

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("TWELVEDATA_TOKEN")
        if not self.token:
            raise AuthenticationError(
                "Twelve Data API token not provided. Set the TWELVEDATA_TOKEN "
                "environment variable (e.g. in .env) or pass token= explicitly."
            )
        self._session: Optional[aiohttp.ClientSession] = None

    async def connect(self) -> None:
        """Establish connection and validate the API token.

        A tiny ``time_series`` request is issued purely to verify the token;
        an invalid key is reported by Twelve Data as ``status != "ok"`` with
        a 401-style message, which we surface as ``AuthenticationError``.
        """
        try:
            self._session = aiohttp.ClientSession()
            params = {
                "symbol": "AAPL",
                "interval": "1day",
                "outputsize": 1,
                "apikey": self.token,
            }
            async with self._session.get(
                f"{BASE_URL}/time_series", params=params
            ) as resp:
                payload = await resp.json()
            # Twelve Data returns 200 with a JSON error body for bad keys.
            if isinstance(payload, dict) and payload.get("status") == "error":
                code = payload.get("code", 0)
                if code in (401, 403):
                    raise AuthenticationError(
                        f"Invalid Twelve Data API token: {payload.get('message', '')}"
                    )
                # Non-auth errors during the probe don't necessarily mean the
                # token is bad; surface them but don't abort the session.
        except AuthenticationError:
            # Make sure we don't leak an open session on auth failure.
            if self._session is not None:
                await self._session.close()
                self._session = None
            raise
        except Exception as e:
            if self._session is not None:
                await self._session.close()
                self._session = None
            raise BrokerError(f"Connection failed: {e}")

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
        """Retrieve historical candles from Twelve Data.

        Args:
            instrument: Ticker symbol as expected by Twelve Data (e.g.
                "AAPL", "MSFT", "ETH/BTC").
            timeframe: Project-wide timeframe (same values as T-Bank:
                "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M").
            from_dt: Start datetime (inclusive).
            to_dt: End datetime (inclusive).
            limit: Optional cap on the number of returned candles.
            offset: Unused by Twelve Data REST; accepted for interface parity.
        """
        if not self._session:
            raise BrokerError("Not connected.")

        interval = TIMEFRAME_MAP.get(timeframe)
        if interval is None:
            raise ValueError(
                f"Unsupported timeframe: {timeframe!r}. "
                f"Supported values: {', '.join(TIMEFRAME_MAP)}."
            )

        params = {
            "symbol": instrument,
            "interval": interval,
            "start_date": from_dt.strftime(_TS_DUMP_FORMAT),
            "end_date": to_dt.strftime(_TS_DUMP_FORMAT),
            "format": "JSON",
            "apikey": self.token,
        }
        # When the caller asks for a bounded number of points, let the API do
        # the trimming. Otherwise Twelve Data caps the response on its own.
        if limit:
            params["outputsize"] = limit

        async with self._session.get(
            f"{BASE_URL}/time_series", params=params
        ) as resp:
            payload = await resp.json()

        if isinstance(payload, dict) and payload.get("status") == "error":
            code = payload.get("code", 0)
            message = payload.get("message", "")
            if code in (401, 403):
                raise AuthenticationError(f"Invalid Twelve Data API token: {message}")
            if code == 429:
                raise RateLimitError(f"Twelve Data rate limit exceeded: {message}")
            if code in (400, 404):
                raise InvalidInstrumentError(
                    f"Instrument not available on Twelve Data ({instrument!r}): {message}"
                )
            raise BrokerError(f"Twelve Data error {code}: {message}")

        values = payload.get("values") if isinstance(payload, dict) else None
        if not values:
            return []

        candles: List[Candle] = []
        for row in values:
            candles.append(self._convert_candle(row))

        # Twelve Data returns newest-first; flip to oldest-first to match the
        # chronological ordering expected by the engine/strategies.
        candles.reverse()

        if limit:
            candles = candles[:limit]
        return candles

    def _convert_candle(self, row: dict) -> Candle:
        """Convert a Twelve Data row dict into the unified Candle model.

        Twelve Data uses different timestamp shapes per interval: intraday rows
        carry ``"YYYY-MM-DD HH:MM:SS"``, while daily/weekly/monthly rows carry
        only ``"YYYY-MM-DD"``. Both are accepted here.
        """
        ts = _parse_timestamp(row["datetime"])
        timestamp_str = ts.strftime("%Y-%m-%dT%H:%M:%S")
        volume = row.get("volume")
        return Candle(
            timestamp=timestamp_str,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(volume) if volume not in (None, "") else 0.0,
        )

    async def place_order(self, instrument, action, quantity, price=None):
        """Place order - not implemented."""
        raise NotImplementedError("Order placement not yet implemented")

    async def get_portfolio(self, account_id=None):
        """Get portfolio - not implemented."""
        raise NotImplementedError("Portfolio retrieval not yet implemented")
