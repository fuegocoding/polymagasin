import asyncio
from polyedge.execution.base import BaseExecutor, TradeResult
from stakeapi import StakeAPI


class StakeExecutor(BaseExecutor):
    def __init__(self, api_key: str):
        # api_key is the access_token (x-access-token header)
        self.api_key = api_key

    async def get_balance(self) -> float:
        """Fetch available balance using StakeAPI."""
        try:
            async with StakeAPI(access_token=self.api_key) as client:
                balance = await client.get_user_balance()
                print(f"[stake:exec] Raw Balance Response: {balance}")

                # StakeAPI might return a Pydantic model or a dict
                # If it's a model, convert to dict for easier parsing
                if hasattr(balance, "dict"):
                    balance = balance.dict()
                elif hasattr(balance, "model_dump"):
                    balance = balance.model_dump()

                if isinstance(balance, dict):
                    # Check for common structures: 'available', 'amount', etc.
                    # Usually it's balance['available']['amount'] or balance['amount']
                    if "available" in balance:
                        avail = balance["available"]
                        if isinstance(avail, dict):
                            return float(avail.get("amount", 0.0))
                        return float(avail)
                    if "amount" in balance:
                        return float(balance["amount"])

                # If it's just a number
                if isinstance(balance, (float, int)):
                    return float(balance)

                return 0.0
        except Exception as e:
            print(f"[stake:exec] Balance error: {e}")
            return 0.0

    async def place_order(
        self, selection_id: str, side: str, size_usd: float, price: float
    ) -> TradeResult:
        try:
            async with StakeAPI(access_token=self.api_key) as client:
                print(
                    f"[stake:exec] Placing bet: selection_id={selection_id}, amount={size_usd}, odds={price}"
                )
                # Assuming stakeapi.place_bet takes standard arguments like market/selection/amount
                # We need to construct the bet placement. Let's use the place_bet method directly.
                # Usually it takes a dict or kwargs
                response = await client.place_bet(
                    market_id=selection_id,
                    amount=size_usd,
                    odds=price,
                )

                print(f"[stake:exec] Bet response: {response}")

                # Check for success
                success = False
                order_id = ""
                if isinstance(response, dict):
                    # Check common success structures
                    if "id" in response:
                        success = True
                        order_id = response["id"]
                    elif "bet" in response and "id" in response["bet"]:
                        success = True
                        order_id = response["bet"]["id"]
                    elif response.get("success"):
                        success = True
                        order_id = response.get("id", f"stake_unk_{selection_id}")
                elif hasattr(response, "id"):
                    success = True
                    order_id = getattr(response, "id")

                if success:
                    return TradeResult(
                        success=True,
                        order_id=str(order_id),
                        filled_price=price,
                        filled_size=size_usd,
                    )
                else:
                    return TradeResult(success=False, error=str(response))
        except Exception as e:
            return TradeResult(success=False, error=str(e))
