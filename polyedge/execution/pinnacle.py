import httpx
from polyedge.execution.base import BaseExecutor, TradeResult

class PinnacleExecutor(BaseExecutor):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.pinnacle.com/v1"
        self.headers = {
            "Authorization": f"Basic {api_key}",
            "Content-Type": "application/json"
        }

    async def get_balance(self) -> float:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.base_url}/client/balance", headers=self.headers)
                print(f"[pinnacle:exec] Balance Fetch Status: {resp.status_code}")
                if resp.status_code != 200:
                    print(f"[pinnacle:exec] Error Body: {resp.text}")
                    return 0.0
                
                data = resp.json()
                print(f"[pinnacle:exec] Raw Balance Response: {data}")
                
                # 'availableBalance' is the standard field name
                return float(data.get("availableBalance", 0.0))
        except Exception as e:
            print(f"[pinnacle:exec] Balance error: {e}")
            return 0.0

    async def place_order(self, selection_id: str, side: str, size_usd: float, price: float) -> TradeResult:
        try:
            return TradeResult(success=True, order_id=f"pinn_sim_{selection_id}")
        except Exception as e:
            return TradeResult(success=False, error=str(e))
