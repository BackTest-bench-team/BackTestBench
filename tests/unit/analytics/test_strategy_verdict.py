from src.analytics.strategy_verdict import build_strategy_verdict
from src.engine.models import MetricsReport


def _metrics(**overrides):
    base = {
        "strategy_id": "demo",
        "instrument": "SBER",
        "total_pnl": 20_000.0,
        "sharpe_ratio": 1.2,
        "max_drawdown": 0.1,
        "win_rate": 0.55,
        "deposit_baseline_pnl": 5_000.0,
        "profit_factor": 1.4,
        "calmar_ratio": 0.8,
        "consistency_pct": 0.75,
        "total_return_pct": 0.2,
        "vs_buy_hold_pct": 0.03,
        "positive_months": 3,
        "total_months": 4,
    }
    base.update(overrides)
    return MetricsReport(**base)


def test_strategy_verdict_pass():
    verdict = build_strategy_verdict(_metrics(), initial_capital=100_000.0)
    assert verdict.grade == "PASS"
    assert verdict.flags == []


def test_strategy_verdict_fail_on_deposit_and_profit_factor():
    verdict = build_strategy_verdict(
        _metrics(total_pnl=1_000.0, deposit_baseline_pnl=5_000.0, profit_factor=0.8),
        initial_capital=100_000.0,
    )
    assert verdict.grade == "FAIL"
    assert "below_deposit_baseline" in verdict.flags
    assert "profit_factor_below_1" in verdict.flags
