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
                if hasattr(balance, 'dict'):
                    balance = balance.dict()
                elif hasattr(balance, 'model_dump'):
                    balance = balance.model_dump()
                
                if isinstance(balance, dict):
                    # Check for common structures: 'available', 'amount', etc.
                    # Usually it's balance['available']['amount'] or balance['amount']
                    if 'available' in balance:
                        avail = balance['available']
                        if isinstance(avail, dict):
                            return float(avail.get('amount', 0.0))
                        return float(avail)
                    if 'amount' in balance:
                        return float(balance['amount'])
                
                # If it's just a number
                if isinstance(balance, (float, int)):
                    return float(balance)
                    
                return 0.0
        except Exception as e:
            print(f"[stake:exec] Balance error: {e}")
            return 0.0

    async def place_order(self, market_id: str, side: str, size_usd: float, price: float) -> TradeResult:
        try:
            async with StakeAPI(access_token=self.api_key) as client:
                # Simulation placeholder
                return TradeResult(success=True, order_id=f"stake_sim_{market_id}")
        except Exception as e:
            return TradeResult(success=False, error=str(e))
