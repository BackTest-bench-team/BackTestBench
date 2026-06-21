from dataclasses import dataclass
from typing import Optional


@dataclass
class Portfolio:
    cash: float
    position_size: float = 0.0
    average_entry_price: float = 0.0
    equity: float = 0.0
    opened_at: Optional[str] = None

    def update_equity(self, current_price: float):
        position_value = self.position_size * current_price
        self.equity = self.cash + position_value
        return self.equity
