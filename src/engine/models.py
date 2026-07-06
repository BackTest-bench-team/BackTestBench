from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict, List
from src.engine.portfolio import Portfolio

@dataclass
class Candle:
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Signal:
    type: str
    size: float = 1.0


@dataclass
class Trade:
    timestamp: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    pnl: float
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None


@dataclass
class TradeLog:
    strategy_id: str
    instrument: str
    trades: list[Trade] = field(default_factory=list)
    final_portfolio_value: float = 0.0
    equity_curve: list[float] = field(default_factory=list)


@dataclass
class RunContext:
    run_id: str
    strategy_id: str
    strategy_version: str
    instrument: str
    timeframe: str
    period_start: datetime | str
    period_end: datetime | str
    initial_capital: float


@dataclass
class MetricsReport:
    strategy_id: str
    instrument: str
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    deposit_baseline_pnl: float

@dataclass(frozen=True)
class OptimizationIteration:
    """Contract representing a single optimization attempt (iteration) during the random search."""
    iteration_index: int              # Attempt number (1, 2, 3, ...)
    params: Dict[str, Any]            # Generated parameter set (e.g. {"fast": 10, "slow": 50})
    metrics: MetricsReport            # Calculated performance metrics (PnL, Sharpe, Drawdown, ...)
    score: float                      # Primary optimization score (e.g. Sharpe Ratio)

@dataclass(frozen=True)
class OptimizationResult:
    """Main output contract of the RandomSearchExecutionEngine optimization process."""
    strategy_id: str                  # Strategy identifier (e.g. "ma_rsi_composable")
    instrument: str                   # Asset ticker (e.g. "SBER")
    target_metric: str                # Metric used for optimization (e.g. "total_pnl")
    
    # --- Best optimization result ---
    best_params: Dict[str, Any]       # Best parameter combination found
    best_metrics: MetricsReport       # Metrics of the best parameter combination
    best_trade_log_report: TradeLog   # Trade log report of the best simulation
    best_equity_curve: List[float]    # Equity curve of the best simulation
    best_final_portfolio: Portfolio   # Final portfolio of the best simulation
    
    # --- Optimization history ---
    iterations: List[OptimizationIteration]  # All optimization attempts (including the best and the worst)
    total_iterations_run: int         # Total number of unique parameter combinations evaluated