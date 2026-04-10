from __future__ import annotations
import httpx
from polyedge.execution.base import BaseExecutor, TradeResult

_URLS = [
    "https://api.stake.com/graphql",
    "https://stake.com/_api/graphql",
]

_BALANCE_QUERY = """
query VaultBalances {
  user {
    balances {
      amount
      available
      currency
    }
  }
}
"""

_BET_MUTATION = """
mutation SportBet($outcomeId: String!, $stake: Float!, $odds: Float!) {
  sportBet(input: {outcomeId: $outcomeId, stake: $stake, odds: $odds}) {
    id
    status
    odds
    stake
  }
}
"""


class StakeExecutor(BaseExecutor):
    def __init__(self, api_key: str):
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        h = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "https://stake.com",
            "Referer": "https://stake.com/",
            "User-Agent": "Mozilla/5.0",
        }
        if self.api_key:
            h["x-access-token"] = self.api_key
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def _post(self, payload: dict) -> dict:
        last: Exception | None = None
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for url in _URLS:
                try:
                    resp = await client.post(url, json=payload, headers=self._headers())
                    resp.raise_for_status()
                    return resp.json()
                except Exception as e:
                    last = e
        if last is not None:
            raise last
        raise RuntimeError("stake request failed: no endpoints configured")

    async def get_balance(self) -> float:
        if not self.api_key:
            return 0.0
        try:
            data = await self._post(
                {"operationName": "VaultBalances", "query": _BALANCE_QUERY, "variables": {}}
            )
            balances = (((data or {}).get("data") or {}).get("user") or {}).get("balances") or []
            for row in balances:
                ccy = str(row.get("currency", "")).upper()
                if ccy in {"USD", "USDT", "USDC"}:
                    return float(row.get("available") or row.get("amount") or 0.0)
            return 0.0
        except Exception as e:
            print(f"[stake:exec] Balance error: {e}")
            return 0.0

    async def place_order(
        self, market_id: str, side: str, size_usd: float, price: float
    ) -> TradeResult:
        if not self.api_key:
            return TradeResult(success=False, error="missing stake_api_key")
        try:
            payload = {
                "operationName": "SportBet",
                "query": _BET_MUTATION,
                "variables": {
                    "outcomeId": market_id,
                    "stake": float(size_usd),
                    "odds": float(price),
                },
            }
            data = await self._post(payload)
            bet = (((data or {}).get("data") or {}).get("sportBet")) or {}
            if not bet:
                return TradeResult(success=False, error=str(data.get("errors") or "bet rejected"))
            return TradeResult(
                success=True,
                order_id=str(bet.get("id") or ""),
                filled_price=float(bet.get("odds") or price),
                filled_size=float(bet.get("stake") or size_usd),
            )
        except Exception as e:
            return TradeResult(success=False, error=str(e))
