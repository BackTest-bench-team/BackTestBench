from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExecutionConfig:
    """Trading costs applied on each fill (percent values, e.g. 0.05 = 0.05%)."""

    commission_pct: float = 0.0
    slippage_pct: float = 0.0

    @classmethod
    def from_dashboard(cls, config: dict[str, Any]) -> ExecutionConfig:
        return cls(
            commission_pct=float(config.get("commission_pct", 0.0)),
            slippage_pct=float(config.get("slippage_pct", 0.0)),
        )
