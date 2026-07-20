from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.engine.models import MetricsReport

Grade = Literal["PASS", "CAUTION", "FAIL"]


@dataclass(frozen=True)
class StrategyVerdict:
    grade: Grade
    flags: list[str]
    vs_buy_hold_pct: float
    vs_deposit_pct: float
    profit_factor: float
    consistency_pct: float
    total_return_pct: float


def build_strategy_verdict(
    metrics: MetricsReport,
    *,
    initial_capital: float,
) -> StrategyVerdict:
    vs_deposit_pct = (
        float(metrics.deposit_baseline_pnl) / initial_capital if initial_capital > 0 else 0.0
    )
    total_return_pct = float(metrics.total_return_pct)
    profit_factor = float(metrics.profit_factor)
    consistency_pct = float(metrics.consistency_pct)
    vs_buy_hold_pct = float(metrics.vs_buy_hold_pct)

    flags: list[str] = []
    if profit_factor < 1.0:
        flags.append("profit_factor_below_1")
    if float(metrics.total_pnl) <= float(metrics.deposit_baseline_pnl):
        flags.append("below_deposit_baseline")
    if vs_buy_hold_pct < 0:
        flags.append("underperforms_buy_hold")
    if consistency_pct < 0.5:
        flags.append("low_consistency")

    if float(metrics.total_pnl) <= float(metrics.deposit_baseline_pnl) or profit_factor < 1.0:
        grade: Grade = "FAIL"
    elif flags:
        grade = "CAUTION"
    else:
        grade = "PASS"

    return StrategyVerdict(
        grade=grade,
        flags=flags,
        vs_buy_hold_pct=vs_buy_hold_pct,
        vs_deposit_pct=vs_deposit_pct,
        profit_factor=profit_factor,
        consistency_pct=consistency_pct,
        total_return_pct=total_return_pct,
    )


def verdict_to_dashboard_dict(verdict: StrategyVerdict) -> dict[str, Any]:
    return {
        "grade": verdict.grade,
        "flags": list(verdict.flags),
        "vs_buy_hold_pct": verdict.vs_buy_hold_pct,
        "vs_deposit_pct": verdict.vs_deposit_pct,
        "profit_factor": verdict.profit_factor,
        "consistency_pct": verdict.consistency_pct,
        "total_return_pct": verdict.total_return_pct,
    }
