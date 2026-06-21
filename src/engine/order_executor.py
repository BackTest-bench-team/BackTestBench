from .models import Trade
from .portfolio import Portfolio
from .types import SignalType


class OrderExecutor:

    def execute(self, signal, portfolio: Portfolio, candle):
        price = candle.close

        # BUY opens a long position. Existing engine behavior is all-in: the
        # signal size is kept for strategy compatibility, but cash determines
        # executable quantity in MVP-1.
        if signal.type == SignalType.BUY:
            if portfolio.cash <= 0 or portfolio.position_size > 0:
                return None

            quantity = portfolio.cash / price

            portfolio.average_entry_price = price
            portfolio.position_size += quantity
            portfolio.cash = 0.0
            portfolio.opened_at = candle.timestamp

            return None

        # SELL closes the current long position.
        if signal.type == SignalType.SELL:
            return self.close_position(portfolio, candle)

        return None

    def close_position(self, portfolio: Portfolio, candle):
        if portfolio.position_size <= 0:
            return None

        price = candle.close
        pnl = portfolio.position_size * (price - portfolio.average_entry_price)

        trade = Trade(
            timestamp=candle.timestamp,
            entry_price=portfolio.average_entry_price,
            exit_price=price,
            quantity=portfolio.position_size,
            pnl=float(pnl),
            opened_at=portfolio.opened_at,
            closed_at=candle.timestamp,
        )

        portfolio.cash += portfolio.position_size * price
        portfolio.position_size = 0.0
        portfolio.average_entry_price = 0.0
        portfolio.opened_at = None

        return trade
