from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum

class EffectType(Enum):
    STOP_LOSS = "SL"
    TAKE_PROFIT = "TP"

@dataclass
class PositionEffect:
    type: EffectType
    level: float  # Trigger price level
    size: float   # Position size to close (e.g. 1.0 means the entire position)

@dataclass
class Portfolio:
    cash: float
    position_size: float = 0.0
    average_entry_price: float = 0.0
    equity: float = 0.0
    opened_at: Optional[str] = None
    effects: List[PositionEffect] = field(default_factory=list) # Новое поле

    def add_effect(self, effect: PositionEffect):
        self.effects.append(effect)

    def clear_effects(self):
        self.effects = []
    
    def update_equity(self, current_price: float):
        position_value = self.position_size * current_price
        self.equity = self.cash + position_value
        return self.equity
