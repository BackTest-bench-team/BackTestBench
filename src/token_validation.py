"""Validate broker API tokens."""

from __future__ import annotations

import asyncio
from typing import Any

from src.broker_adapter.base import AuthenticationError, BrokerError
from src.broker_adapter.tbank import TBankAdapter
from src.broker_adapter.twelvedata import TwelveDataAdapter


async def _validate_tinkoff(token: str) -> dict[str, Any]:
    adapter = TBankAdapter(token=token, verify_ssl=False)
    try:
        await adapter.connect()
        return {"valid": True, "message": "T-Bank token verified"}
    except AuthenticationError as exc:
        return {"valid": False, "message": str(exc)}
    except BrokerError as exc:
        return {"valid": False, "message": str(exc)}
    except Exception as exc:
        return {"valid": False, "message": f"Verification failed: {exc}"}
    finally:
        await adapter.disconnect()


async def _validate_twelvedata(token: str) -> dict[str, Any]:
    adapter = TwelveDataAdapter(token=token)
    try:
        await adapter.connect()
        return {"valid": True, "message": "Twelve Data token verified"}
    except AuthenticationError as exc:
        return {"valid": False, "message": str(exc)}
    except BrokerError as exc:
        return {"valid": False, "message": str(exc)}
    except Exception as exc:
        return {"valid": False, "message": f"Verification failed: {exc}"}
    finally:
        await adapter.disconnect()


async def validate_tokens(tokens: dict[str, str]) -> dict[str, dict[str, Any]]:
    tasks: dict[str, Any] = {}
    if tokens.get("TINKOFF_TOKEN"):
        tasks["TINKOFF_TOKEN"] = _validate_tinkoff(tokens["TINKOFF_TOKEN"])
    if tokens.get("TWELVEDATA_TOKEN"):
        tasks["TWELVEDATA_TOKEN"] = _validate_twelvedata(tokens["TWELVEDATA_TOKEN"])

    if not tasks:
        return {}

    keys = list(tasks.keys())
    results = await asyncio.gather(*tasks.values())
    return {key: result for key, result in zip(keys, results, strict=True)}


def validate_tokens_sync(tokens: dict[str, str]) -> dict[str, dict[str, Any]]:
    return asyncio.run(validate_tokens(tokens))
