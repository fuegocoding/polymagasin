import asyncio
import os
from polyedge.execution.base import BaseExecutor, TradeResult
from py_clob_client.client import ClobClient
from py_clob_client.constants import POLYGON
from py_clob_client.clob_types import OrderArgs

class PolymarketExecutor(BaseExecutor):
    def __init__(self, private_key: str):
        self.private_key = private_key
        host = "https://clob.polymarket.com"
        chain_id = POLYGON
        # Note: Production usage often requires API Key/Secret/Passphrase
        # but for balance checks, the private key alone can often initialize the client
        self.client = ClobClient(host, chain_id=chain_id, private_key=private_key)

    async def get_balance(self) -> float:
        """Fetch USDC collateral balance from Polymarket CLOB."""
        try:
            loop = asyncio.get_event_loop()
            # The SDK uses get_collateral_balance to check how much USDC is in the CLOB
            # Note: This checks the user's allowance and balance on-chain or in the proxy
            resp = await loop.run_in_executor(None, self.client.get_collateral_balance)
            if resp and "balance" in resp:
                return float(resp["balance"])
            return 0.0
        except Exception as e:
            print(f"[poly:exec] Balance error: {e}")
            return 0.0

    async def place_order(self, token_id: str, side: str, size_usd: float, price: float) -> TradeResult:
        try:
            loop = asyncio.get_event_loop()
            amount = size_usd / price
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=amount,
                side="BUY"
            )
            resp = await loop.run_in_executor(None, lambda: self.client.create_order(order_args))
            if isinstance(resp, dict) and resp.get("success"):
                return TradeResult(success=True, order_id=resp.get("orderID"), filled_price=price, filled_size=amount)
            else:
                return TradeResult(success=False, error=str(resp))
        except Exception as e:
            return TradeResult(success=False, error=str(e))
