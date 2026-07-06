import itertools
import random
from typing import Any, Dict, List

from src.analytics import calculate_metrics_from_trade_log
from src.engine.execution_engine import ExecutionEngine
from src.engine.models import (
    Candle,
    MetricsReport,
    OptimizationIteration,
    OptimizationResult,
    RunContext,
)
from src.strategy import create_strategy


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
        target_metric: str = "total_pnl"
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

        # Generate the full grid of all unique parameter combinations.
        param_names = list(search_space.keys())
        all_combinations_tuples = list(itertools.product(*(search_space[name] for name in param_names)))

        # Select random unique combinations without repetition.
        if len(all_combinations_tuples) <= n_iterations:
            chosen_combinations = all_combinations_tuples
            random.shuffle(chosen_combinations)
        else:
            chosen_combinations = random.sample(all_combinations_tuples, n_iterations)

        best_score = float("-inf")
        best_params: Dict[str, Any] = {}
        best_metrics: MetricsReport | None = None
        best_raw_result: Dict[str, Any] = {}
        iterations_list: List[OptimizationIteration] = []

        # Execute the optimization loop.
        for idx, combo in enumerate(chosen_combinations, start=1):
            current_params = dict(fixed_params)
            for name, val in zip(param_names, combo):
                current_params[name] = val

            try:
                strategy = create_strategy(strategy_id, current_params)
                raw_result = self.base_engine.run(strategy, candles, initial_capital)
                
                # Проверка: если сделок нет, пропускаем как неудачный прогон
                if not raw_result.get("trade_log_report") or not raw_result["trade_log_report"].trades:
                    continue
                    
                metrics = calculate_metrics_from_trade_log(raw_result["trade_log_report"], run_context)
            except Exception as e:
                print(f"Iteration {idx} failed: {e}")
                continue # Skip failed iterations

            score = float(getattr(metrics, target_metric, metrics.total_pnl))

            # Store the current optimization iteration.
            iteration_record = OptimizationIteration(
                iteration_index=idx,
                params=current_params,
                metrics=metrics,
                score=score
            )
            iterations_list.append(iteration_record)

            # Update the current best result if this iteration performs better.
            if score > best_score or best_metrics is None:
                best_score = score
                best_params = current_params
                best_metrics = metrics
                best_raw_result = raw_result

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