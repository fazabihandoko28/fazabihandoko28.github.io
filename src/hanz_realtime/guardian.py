from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Tick


@dataclass
class PositionState:
    symbol: str
    market: str
    entry_price: float
    quantity: float
    stop_price: float
    target_price: float | None = None
    trailing_pct: float | None = None
    highest_price: float | None = None
    status: str = "TAHAN"
    updated_at: datetime | None = None


class PortfolioGuardian:
    def __init__(self) -> None:
        self.positions: dict[tuple[str, str], PositionState] = {}

    def add_position(self, position: PositionState) -> None:
        if position.entry_price <= 0:
            raise ValueError("entry_price must be positive")
        if position.quantity <= 0:
            raise ValueError("quantity must be positive")
        self.positions[(position.market, position.symbol)] = position

    def on_tick(self, tick: Tick) -> str | None:
        position = self.positions.get((tick.market, tick.symbol))
        if position is None:
            return None

        position.updated_at = tick.timestamp
        position.highest_price = max(position.highest_price or tick.price, tick.price)

        if position.trailing_pct is not None and position.highest_price:
            dynamic_stop = position.highest_price * (1.0 - position.trailing_pct / 100.0)
            position.stop_price = max(position.stop_price, dynamic_stop)

        if tick.price <= position.stop_price:
            position.status = "JUAL"
        elif position.target_price is not None and tick.price >= position.target_price:
            position.status = "LEPAS"
        elif position.entry_price and tick.price < position.entry_price * 0.985:
            position.status = "LEPAS"
        else:
            position.status = "TAHAN"

        return position.status
