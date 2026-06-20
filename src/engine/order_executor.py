from engine.models import Trade
from engine.portfolio import Portfolio
from engine.types import SignalType


class OrderExecutor:

    def execute(self, signal, portfolio: Portfolio, candle):

        price = candle.close

        # BUY
        if signal.type == SignalType.BUY:

            quantity = portfolio.cash / price

            portfolio.average_entry_price = price
            portfolio.position_size += quantity
            portfolio.cash = 0

            return None

        # SELL
        if signal.type == SignalType.SELL:

            pnl = portfolio.position_size * (price - portfolio.average_entry_price)

            trade = Trade(
                timestamp=candle.timestamp,
                entry_price=portfolio.average_entry_price,
                exit_price=price,
                quantity=portfolio.position_size,
                pnl=pnl
            )

            portfolio.cash += portfolio.position_size * price
            portfolio.position_size = 0
            portfolio.average_entry_price = 0

            return trade

        return None