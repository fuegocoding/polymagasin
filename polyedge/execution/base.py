from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TradeResult:
    success: bool
    order_id: str | None = None
    filled_price: float | None = None
    filled_size: float | None = None
    error: str | None = None

class BaseExecutor(ABC):
    @abstractmethod
    async def get_balance(self) -> float:
        """Return available liquid balance in USD/USDC."""
        pass

    @abstractmethod
    async def place_order(self, market_id: str, side: str, size_usd: float, price: float) -> TradeResult:
        """Place a market or limit order."""
        pass
