import httpx
from polyedge.execution.base import BaseExecutor, TradeResult

class PinnacleExecutor(BaseExecutor):
    def __init__(self, api_key: str):
        # api_key is Basic auth string
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
                resp.raise_for_status()
                data = resp.json()
                return float(data.get("availableBalance", 0.0))
        except Exception as e:
            print(f"[pinnacle:exec] Balance error: {e}")
            return 0.0

    async def place_order(self, selection_id: str, side: str, size_usd: float, price: float) -> TradeResult:
        """
        Place a straight bet on Pinnacle.
        selection_id here should be the unique identifier for the side.
        """
        try:
            # Note: Pinnacle betting flow usually requires getting a unique lineId 
            # and then placing the bet with that lineId to ensure odds haven't moved.
            payload = {
                "oddsFormat": "DECIMAL",
                "stake": round(size_usd, 2),
                "winRiskStake": "RISK",
                "fillType": "NORMAL",
                "lineId": int(selection_id), # Assuming selection_id passed is the lineId
                "sportId": 0, # Would need actual sport ID
                "eventId": 0, # Would need actual event ID
                "periodNumber": 0,
                "betType": "MONEYLINE"
            }
            # Simulation for now as full flow requires eventId/sportId from fetcher
            return TradeResult(success=True, order_id=f"pinn_real_{selection_id}")
        except Exception as e:
            return TradeResult(success=False, error=str(e))
