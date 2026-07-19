from .execution_config import ExecutionConfig
from .models import Trade
from .portfolio import Portfolio
from .types import SignalType


class OrderExecutor:

    def __init__(self, execution_config: ExecutionConfig | None = None):
        self.config = execution_config or ExecutionConfig()

    def _buy_price(self, close: float) -> float:
        return close * (1.0 + self.config.slippage_pct / 100.0)

    def _sell_price(self, close: float) -> float:
        return close * (1.0 - self.config.slippage_pct / 100.0)

    def execute(self, signal, portfolio: Portfolio, candle):
        price = candle.close

        # BUY opens a long position. Existing engine behavior is all-in: the
        # signal size is kept for strategy compatibility, but cash determines
        # executable quantity in MVP-1.
        if signal.type == SignalType.BUY:
            if portfolio.cash <= 0 or portfolio.position_size > 0:
                return None

            buy_price = self._buy_price(price)
            cost_basis = portfolio.cash
            commission = cost_basis * (self.config.commission_pct / 100.0)
            spendable = cost_basis - commission
            if spendable <= 0 or buy_price <= 0:
                return None

            quantity = spendable / buy_price

            portfolio.average_entry_price = buy_price
            portfolio.cost_basis = cost_basis
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

        sell_price = self._sell_price(candle.close)
        gross = portfolio.position_size * sell_price
        commission = gross * (self.config.commission_pct / 100.0)
        net_proceeds = gross - commission
        entry_cost = portfolio.cost_basis if portfolio.cost_basis > 0 else (
            portfolio.position_size * portfolio.average_entry_price
        )
        pnl = net_proceeds - entry_cost

        trade = Trade(
            timestamp=candle.timestamp,
            entry_price=portfolio.average_entry_price,
            exit_price=sell_price,
            quantity=portfolio.position_size,
            pnl=float(pnl),
            opened_at=portfolio.opened_at,
            closed_at=candle.timestamp,
        )

        portfolio.cash += net_proceeds
        portfolio.position_size = 0.0
        portfolio.average_entry_price = 0.0
        portfolio.cost_basis = 0.0
        portfolio.opened_at = None

        return trade
