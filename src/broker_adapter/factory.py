"""Broker adapter factory for dashboard and CLI runtime."""

from __future__ import annotations

import os
from typing import Any, Optional

from .bybit import BybitAdapter
from .tbank import TBankAdapter
from .twelvedata import TwelveDataAdapter

SUPPORTED_SOURCES: tuple[str, ...] = ("tbank", "twelvedata", "bybit")

TOKEN_ENV_BY_SOURCE: dict[str, str] = {
    "tbank": "TINKOFF_TOKEN",
    "twelvedata": "TWELVEDATA_TOKEN",
    "bybit": "BYBIT_TOKEN",
}

OPTIONAL_TOKEN_SOURCES: frozenset[str] = frozenset({"bybit"})

SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "tbank": "T-Bank",
    "twelvedata": "Twelve Data",
    "bybit": "Bybit",
}


def source_display_name(source: str) -> str:
    return SOURCE_DISPLAY_NAMES.get(source, source)


def resolve_source(source: Optional[str], *, default: str = "tbank") -> str:
    resolved = (source or default).strip().lower()
    if resolved not in SUPPORTED_SOURCES:
        raise ValueError(
            f"Unsupported data source {source!r}. "
            f"Supported values: {', '.join(SUPPORTED_SOURCES)}."
        )
    return resolved


def get_token(source: str) -> Optional[str]:
    resolved = resolve_source(source)
    env_var = TOKEN_ENV_BY_SOURCE[resolved]
    token = os.getenv(env_var)
    if not token:
        if resolved in OPTIONAL_TOKEN_SOURCES:
            return None
        raise RuntimeError(
            f"{env_var} is not set. Add it to .env (see .env.example) "
            f"or set the environment variable."
        )
    return token


def token_configured(source: str) -> bool:
    resolved = resolve_source(source)
    if resolved in OPTIONAL_TOKEN_SOURCES:
        return True
    return bool(os.getenv(TOKEN_ENV_BY_SOURCE[resolved]))


def build_adapter(source: str, token: Optional[str] = None, **kwargs: Any) -> Any:
    resolved = resolve_source(source)
    if token is None:
        token = get_token(resolved)

    if resolved == "tbank":
        return TBankAdapter(token=token, verify_ssl=False, **kwargs)
    if resolved == "bybit":
        return BybitAdapter(token=token)
    return TwelveDataAdapter(token=token)
