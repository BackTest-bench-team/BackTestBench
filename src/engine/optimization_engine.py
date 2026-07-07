import itertools
import random
from typing import Any, Callable, Dict, List, Optional

from src.analytics import calculate_metrics_from_trade_log
from src.engine.execution_engine import ExecutionEngine
from src.engine.models import (
    Candle,
    MetricsReport,
    OptimizationIteration,
    OptimizationResult,
    Portfolio,
    RunContext,
    TradeLog,
)
from src.strategy import create_strategy


def is_valid_param_combo(params: Dict[str, Any]) -> bool:
    fast = params.get("fast")
    slow = params.get("slow")
    if fast is not None and slow is not None and float(fast) >= float(slow):
        return False

    rsi_min = params.get("rsi_buy_min")
    rsi_max = params.get("rsi_overbought")
    if rsi_min is not None and rsi_max is not None and float(rsi_min) >= float(rsi_max):
        return False

    return True


class RandomSearchExecutionEngine:

    def __init__(self, base_engine: ExecutionEngine | None = None):
        self.base_engine = base_engine or ExecutionEngine()

    def run_optimization(
        self,
        strategy_id: str,
        param_grid: Dict[str, Any],
        candles: List[Candle],
        initial_capital: float,
        run_context: RunContext,
        n_iterations: int = 10,
        target_metric: str = "total_pnl",
        seed: int = 42,
        mode: str = "grid",
        should_stop: Optional[Callable[[], bool]] = None,
    ) -> OptimizationResult:
        
        fixed_params = {}
        search_space = {}

        # Split parameters into fixed values and searchable parameter lists.
        for key, val in param_grid.items():
            if isinstance(val, (list, tuple)) and len(val) > 0:
                search_space[key] = list(val)
            else:
                fixed_params[key] = val

        instrument = run_context.instrument or getattr(candles[0], "instrument", "") if candles else ""

        # Edge case: if there are no searchable parameters,
        # execute a single baseline simulation.
        if not search_space:
            strategy = create_strategy(strategy_id, fixed_params)
            raw_result = self.base_engine.run(strategy, candles, initial_capital)
            metrics = calculate_metrics_from_trade_log(raw_result["trade_log_report"], run_context)
            score = float(getattr(metrics, target_metric, metrics.total_pnl))
            
            single_iteration = OptimizationIteration(
                iteration_index=1,
                params=fixed_params,
                metrics=metrics,
                score=score
            )
            
            return OptimizationResult(
                strategy_id=strategy_id,
                instrument=instrument,
                target_metric=target_metric,
                best_params=fixed_params,
                best_metrics=metrics,
                best_trade_log_report=raw_result["trade_log_report"],
                best_equity_curve=raw_result["equity_curve"],
                best_final_portfolio=raw_result["final_portfolio"],
                iterations=[single_iteration],
                total_iterations_run=1
            )

        # Build the list of parameter combinations to evaluate.
        param_names = list(search_space.keys())
        all_combinations_tuples = list(itertools.product(*(search_space[name] for name in param_names)))
        rng = random.Random(seed)

        if mode == "grid":
            chosen_combinations = all_combinations_tuples
        elif len(all_combinations_tuples) <= n_iterations:
            chosen_combinations = all_combinations_tuples
        else:
            chosen_combinations = rng.sample(all_combinations_tuples, n_iterations)

        best_score = float("-inf")
        best_params: Dict[str, Any] = {}
        best_metrics: MetricsReport | None = None
        best_raw_result: Dict[str, Any] = {}
        iterations_list: List[OptimizationIteration] = []
        skipped_invalid = 0

        # Execute the optimization loop.
        run_index = 0
        for combo in chosen_combinations:
            if should_stop and should_stop():
                break

            current_params = dict(fixed_params)
            for name, val in zip(param_names, combo):
                current_params[name] = val

            if not is_valid_param_combo(current_params):
                skipped_invalid += 1
                continue

            run_index += 1

            try:
                strategy = create_strategy(strategy_id, current_params)
                raw_result = self.base_engine.run(strategy, candles, initial_capital)

                if not raw_result.get("trade_log_report") or not raw_result["trade_log_report"].trades:
                    continue

                metrics = calculate_metrics_from_trade_log(raw_result["trade_log_report"], run_context)
            except Exception as e:
                print(f"Iteration {run_index} failed: {e}")
                continue

            score = float(getattr(metrics, target_metric, metrics.total_pnl))

            iteration_record = OptimizationIteration(
                iteration_index=run_index,
                params=current_params,
                metrics=metrics,
                score=score,
            )
            iterations_list.append(iteration_record)

            if score > best_score or best_metrics is None:
                best_score = score
                best_params = current_params
                best_metrics = metrics
                best_raw_result = raw_result

        if skipped_invalid:
            print(f"Skipped {skipped_invalid} invalid parameter combinations")

        if not best_raw_result:
            best_raw_result = {
                "trade_log_report": TradeLog(
                    strategy_id=strategy_id,
                    instrument=instrument,
                    trades=[],
                    final_portfolio_value=initial_capital,
                    equity_curve=[initial_capital],
                ),
                "equity_curve": [initial_capital],
                "final_portfolio": Portfolio(cash=initial_capital),
            }

        # Return the final optimization result.
        return OptimizationResult(
            strategy_id=strategy_id,
            instrument=instrument,
            target_metric=target_metric,
            best_params=best_params,
            best_metrics=best_metrics,
            best_trade_log_report=best_raw_result["trade_log_report"],
            best_equity_curve=best_raw_result["equity_curve"],
            best_final_portfolio=best_raw_result["final_portfolio"],
            iterations=iterations_list,
            total_iterations_run=len(iterations_list)
        )