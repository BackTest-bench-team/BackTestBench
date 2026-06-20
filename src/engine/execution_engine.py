from typing import List

from engine.models import Candle, Trade
from engine.portfolio import Portfolio
from engine.context import ExecutionContext
from engine.order_executor import OrderExecutor


class ExecutionEngine:

    def __init__(self):
        self.executor = OrderExecutor()

    def run(
        self,
        strategy,
        candles: List[Candle],
        initial_capital: float
    ):

        portfolio = Portfolio(cash=initial_capital)

        trade_log: List[Trade] = []

        for i in range(len(candles)):

            candle = candles[i]

            historical = candles[:i]

            context = ExecutionContext(
                current_candle=candle,
                historical_candles=historical,
                portfolio=portfolio
            )

            signal = strategy.on_candle(context)

            trade = self.executor.execute(
                signal,
                portfolio,
                candle
            )

            if trade:
                trade_log.append(trade)

            portfolio.update_equity(candle.close)

        return {
            "trade_log": trade_log,
            "final_portfolio": portfolio
        }