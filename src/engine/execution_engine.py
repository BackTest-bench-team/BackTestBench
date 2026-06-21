from typing import List

from .models import Candle, Trade, TradeLog
from .portfolio import Portfolio
from .context import ExecutionContext
from .order_executor import OrderExecutor


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
        portfolio.update_equity(candles[0].close if candles else 0.0)

        trade_log: List[Trade] = []
        equity_curve: list[float] = [float(initial_capital)]

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
            equity_curve.append(float(portfolio.equity))

        # MVP-1 rule: any open long position is force-closed on the last candle
        # close so realized P&L equals final portfolio value - initial capital.
        if candles and portfolio.position_size > 0:
            final_trade = self.executor.close_position(portfolio, candles[-1])
            if final_trade:
                trade_log.append(final_trade)
            portfolio.update_equity(candles[-1].close)
            equity_curve[-1] = float(portfolio.equity)

        report = TradeLog(
            strategy_id=getattr(strategy, "strategy_id", ""),
            instrument=getattr(strategy, "instrument", ""),
            trades=trade_log,
            final_portfolio_value=float(portfolio.equity),
            equity_curve=equity_curve,
        )

        return {
            "trade_log": trade_log,
            "trade_log_report": report,
            "equity_curve": equity_curve,
            "final_portfolio": portfolio,
        }
