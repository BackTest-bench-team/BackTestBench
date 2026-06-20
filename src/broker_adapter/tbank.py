"""
T-Bank (Tinkoff Investments) Broker Adapter implementation.

This module implements the BrokerAdapter interface using gRPC/HTTP
for T-Bank Invest API v2 with real data.
"""

import os
import sys
import ssl
import struct
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict
from pathlib import Path

import aiohttp
from google.protobuf import timestamp_pb2

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "generated"))

import marketdata_pb2
import instruments_pb2
import users_pb2

from .base import BrokerAdapter, BrokerError, AuthenticationError, InvalidInstrumentError, RateLimitError
from .models import Candle, OrderResult, Position, Portfolio

TIMEFRAME_MAP = {
    "1m": marketdata_pb2.CANDLE_INTERVAL_1_MIN,
    "5m": marketdata_pb2.CANDLE_INTERVAL_5_MIN,
    "15m": marketdata_pb2.CANDLE_INTERVAL_15_MIN,
    "30m": marketdata_pb2.CANDLE_INTERVAL_30_MIN,
    "1h": marketdata_pb2.CANDLE_INTERVAL_HOUR,
    "1d": marketdata_pb2.CANDLE_INTERVAL_DAY,
    "1w": marketdata_pb2.CANDLE_INTERVAL_WEEK,
    "1M": marketdata_pb2.CANDLE_INTERVAL_MONTH,
}


def grpc_frame(message_bytes):
    """Create gRPC frame: 1 byte compression + 4 bytes length + message."""
    compressed = 0
    length = len(message_bytes)
    header = struct.pack(">BI", compressed, length)
    return header + message_bytes


def parse_grpc_frame(raw):
    """Parse gRPC frame and return message bytes."""
    if len(raw) < 5:
        raise BrokerError("Invalid gRPC response: too short")
    length = struct.unpack(">I", raw[1:5])[0]
    if len(raw) < 5 + length:
        raise BrokerError("Invalid gRPC response: incomplete")
    return raw[5:5+length]


def parse_quotation(quotation):
    """Convert Quotation (units + nano) to float."""
    return quotation.units + quotation.nano / 1e9


def serialize_candles_request(figi, from_dt, to_dt, interval):
    """
    Serialize GetCandlesRequest manually to handle 'from' reserved word in Python 3.14+.
    """
    def encode_varint(value):
        result = []
        while value > 0x7f:
            result.append((value & 0x7f) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)
    
    def encode_field(field_number, wire_type, data):
        tag = (field_number << 3) | wire_type
        if wire_type == 0:  # varint
            return encode_varint(tag) + encode_varint(data)
        elif wire_type == 2:  # length-delimited
            return encode_varint(tag) + encode_varint(len(data)) + data
        return b''
    
    from_ts = timestamp_pb2.Timestamp()
    from_ts.FromDatetime(from_dt.replace(tzinfo=timezone.utc))
    to_ts = timestamp_pb2.Timestamp()
    to_ts.FromDatetime(to_dt.replace(tzinfo=timezone.utc))
    
    message = b''
    message += encode_field(1, 2, figi.encode())  # figi
    message += encode_field(2, 2, from_ts.SerializeToString())  # from
    message += encode_field(3, 2, to_ts.SerializeToString())  # to
    message += encode_field(4, 0, interval)  # interval
    return message


class TBankAdapter(BrokerAdapter):
    """Concrete implementation of BrokerAdapter for T-Bank Invest API v2."""
    
    PRODUCTION_HOST = "invest-public-api.tbank.ru"
    SANDBOX_HOST = "sandbox-invest-public-api.tbank.ru"

    def __init__(self, token=None, use_sandbox=False, verify_ssl=False):
        self.token = token or os.getenv("TINKOFF_TOKEN")
        if not self.token:
            raise AuthenticationError("T-Bank API token not provided.")
        self._use_sandbox = use_sandbox
        self._verify_ssl = verify_ssl
        self._session = None

    def _get_base_url(self):
        host = self.SANDBOX_HOST if self._use_sandbox else self.PRODUCTION_HOST
        return f"https://{host}"

    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/grpc+proto",
            "Accept": "application/grpc+proto",
            "TE": "trailers",
        }

    async def connect(self):
        """Establish connection and validate token."""
        try:
            ssl_context = ssl.create_default_context()
            if not self._verify_ssl:
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)

            # Test connection
            request = instruments_pb2.InstrumentRequest(
                id_type=instruments_pb2.INSTRUMENT_ID_TYPE_TICKER,
                class_code="TQBR",
                id="SBER",
            )
            data = grpc_frame(request.SerializeToString())
            url = f"{self._get_base_url()}/tinkoff.public.invest.api.contract.v1.InstrumentsService/ShareBy"
            
            async with self._session.post(url, headers=self._get_headers(), data=data) as resp:
                if resp.headers.get("grpc-status") and resp.headers.get("grpc-status") != "0":
                    raise AuthenticationError("Invalid T-Bank API token")

        except AuthenticationError:
            raise
        except Exception as e:
            raise BrokerError(f"Connection failed: {e}")

    async def disconnect(self):
        """Close connection."""
        if self._session:
            await self._session.close()
            self._session = None

    async def _call_grpc(self, service_method, request_data):
        """Make a gRPC call via HTTP."""
        if not self._session:
            raise BrokerError("Not connected.")
        url = f"{self._get_base_url()}/{service_method}"
        framed_data = grpc_frame(request_data)
        async with self._session.post(url, headers=self._get_headers(), data=framed_data) as resp:
            grpc_status = resp.headers.get("grpc-status")
            grpc_message = resp.headers.get("grpc-message", "")
            raw = await resp.read()
            if grpc_status and grpc_status != "0":
                if int(grpc_status) == 16:
                    raise AuthenticationError("Invalid T-Bank API token")
                elif int(grpc_status) == 8:
                    raise RateLimitError("Rate limit exceeded")
                raise BrokerError(f"gRPC error {grpc_status}: {grpc_message}")
            return parse_grpc_frame(raw)

    async def get_candles(self, instrument, timeframe, from_dt, to_dt, limit=None, offset=None):
        """Retrieve historical candles."""
        if not self._session:
            raise BrokerError("Not connected.")

        candle_interval = TIMEFRAME_MAP.get(timeframe)
        if candle_interval is None:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

        figi = await self._get_figi(instrument)

        request_data = serialize_candles_request(figi, from_dt, to_dt, candle_interval)

        response_data = await self._call_grpc(
            "tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
            request_data,
        )

        response = marketdata_pb2.GetCandlesResponse()
        response.ParseFromString(response_data)

        candles = []
        for hc in response.candles:
            candles.append(self._convert_candle(hc, instrument, timeframe))

        if limit:
            candles = candles[:limit]
        return candles

    async def _get_figi(self, instrument):
        """Convert ticker to FIGI."""
        if instrument.startswith("BBG") or len(instrument) == 12:
            return instrument
        try:
            request = instruments_pb2.InstrumentRequest(
                id_type=instruments_pb2.INSTRUMENT_ID_TYPE_TICKER,
                class_code="TQBR",
                id=instrument,
            )
            response_data = await self._call_grpc(
                "tinkoff.public.invest.api.contract.v1.InstrumentsService/ShareBy",
                request.SerializeToString(),
            )
            response = instruments_pb2.SharesResponse()
            response.ParseFromString(response_data)
            if response.instruments:
                return response.instruments[0].figi
            raise InvalidInstrumentError(f"Instrument not found: {instrument}")
        except InvalidInstrumentError:
            raise
        except Exception as e:
            raise BrokerError(f"Failed to lookup instrument: {e}")

    def _convert_candle(self, historic_candle, instrument, timeframe):
        """Convert HistoricCandle to internal Candle model."""
        ts = historic_candle.time.ToDatetime()
        return Candle(
            instrument=instrument,
            timestamp=ts,
            timeframe=timeframe,
            open=parse_quotation(historic_candle.open),
            high=parse_quotation(historic_candle.high),
            low=parse_quotation(historic_candle.low),
            close=parse_quotation(historic_candle.close),
            volume=float(historic_candle.volume),
        )

    async def place_order(self, instrument, action, quantity, price=None):
        """Place order - not implemented."""
        raise NotImplementedError("Order placement not yet implemented")

    async def get_portfolio(self, account_id=None):
        """Get portfolio - not implemented."""
        raise NotImplementedError("Portfolio retrieval not yet implemented")
