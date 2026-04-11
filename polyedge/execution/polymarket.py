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
        # Initialize client. Note: 'key' is the private key parameter.
        self.client = ClobClient(host, chain_id=chain_id, key=private_key)

    async def get_balance(self) -> float:
        """Fetch USDC collateral balance from Polymarket CLOB."""
        try:
            loop = asyncio.get_event_loop()

            def _fetch():
                from py_clob_client.clob_types import BalanceAllowanceParams, AssetType

                # 1. Derive L2 API credentials
                creds = self.client.derive_api_key()
                # 2. Set the credentials on the client to upgrade to Level 2 Auth
                self.client.set_api_creds(creds)
                # 3. Fetch the collateral balance
                params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
                return self.client.get_balance_allowance(params=params)

            resp = await loop.run_in_executor(None, _fetch)
            print(f"[poly:exec] Raw Balance Response: {resp}")

            if isinstance(resp, dict):
                # Response usually looks like {'balance': '123.45', 'allowance': '...'}
                if "balance" in resp:
                    return float(resp["balance"])
                if "amount" in resp:
                    return float(resp["amount"])

            if isinstance(resp, (str, float, int)):
                return float(resp)

            return 0.0
        except Exception as e:
            print(f"[poly:exec] Balance error: {e}")
            return 0.0

    async def place_order(
        self, token_id: str, side: str, size_usd: float, price: float
    ) -> TradeResult:
        try:
            loop = asyncio.get_event_loop()
            amount = size_usd / price
            order_args = OrderArgs(
                token_id=token_id, price=price, size=amount, side="BUY"
            )

            def _place():
                creds = self.client.derive_api_key()
                self.client.set_api_creds(creds)

                # First create the order (signs it)
                signed_order = self.client.create_order(order_args)
                # Then post the order to the CLOB
                return self.client.post_order(signed_order)

            resp = await loop.run_in_executor(None, _place)
            print(f"[poly:exec] Place order response: {resp}")

            if isinstance(resp, dict) and resp.get("success"):
                return TradeResult(
                    success=True,
                    order_id=resp.get("orderID", "poly_order"),
                    filled_price=price,
                    filled_size=amount,
                )
            else:
                return TradeResult(success=False, error=str(resp))
        except Exception as e:
            return TradeResult(success=False, error=str(e))
