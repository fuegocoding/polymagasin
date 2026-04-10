from __future__ import annotations
from stakeapi import StakeAPI
from stakeapi.exceptions import StakeAPIError
from polyedge.execution.base import BaseExecutor, TradeResult

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

    async def get_balance(self) -> float:
        if not self.api_key:
            return 0.0
        try:
            async with StakeAPI(access_token=self.api_key) as stake:
                balances = await stake.get_user_balance()
            available = balances.get("available") or {}
            for key in ("usd", "usdt", "usdc"):
                if key in available:
                    return float(available[key])
            return 0.0
        except StakeAPIError as e:
            print(f"[stake:exec] Balance error: {e}")
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
            async with StakeAPI(access_token=self.api_key) as stake:
                # StakeAPI's public place_bet() targets a REST endpoint that doesn't
                # support sportsbook mutations. We use _graphql_request() for the SportBet
                # mutation directly. Migrate to a public method if the library adds one.
                data = await stake._graphql_request(
                    _BET_MUTATION,
                    variables={
                        "outcomeId": market_id,
                        "stake": float(size_usd),
                        "odds": float(price),
                    },
                    operation_name="SportBet",
                )
            bet = (data or {}).get("sportBet") or {}
            if not bet:
                return TradeResult(success=False, error="bet rejected by Stake")
            return TradeResult(
                success=True,
                order_id=str(bet.get("id") or ""),
                filled_price=float(bet.get("odds") or price),
                filled_size=float(bet.get("stake") or size_usd),
            )
        except StakeAPIError as e:
            return TradeResult(success=False, error=str(e))
        except Exception as e:
            return TradeResult(success=False, error=str(e))
