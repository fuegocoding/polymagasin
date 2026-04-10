from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team
from stakeapi import StakeAPI

class StakeFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key # This is the x-access-token

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        out = []
        try:
            async with StakeAPI(access_token=self.api_key) as client:
                for sport in sports:
                    # Map common sport names to Stake internal names if needed
                    # StakeAPI typically has get_sports_events
                    events = await client.get_sports_events(sport=sport)
                    for ev in events:
                        line = self._parse_event(ev, sport)
                        if line:
                            out.append(line)
        except Exception as e:
            print(f"[stake:fetch] Error: {e}")
        return out

    def _parse_event(self, ev, sport) -> OddsLine | None:
        try:
            # This is a generic parser based on likely StakeAPI event structure
            # Real implementation would inspect the ev object (Pydantic model)
            home = ev.home_team.name
            away = ev.away_team.name
            # Find moneyline market
            # Stake usually has 'markets' or 'bet_offers'
            for market in getattr(ev, 'markets', []):
                if market.name.lower() in ("moneyline", "match winner", "1x2"):
                    odds = market.selections
                    if len(odds) >= 2:
                        return OddsLine(
                            source="stake",
                            sport=sport,
                            league=getattr(ev, 'league', {}).name or "Unknown",
                            team1=normalize_team(home, sport),
                            team2=normalize_team(away, sport),
                            game_date=ev.start_time,
                            odds_home=odds[0].price,
                            odds_away=odds[1].price,
                            fetched_at=datetime.now(timezone.utc),
                            external_id=str(ev.id),
                            selection_id_home=str(odds[0].id),
                            selection_id_away=str(odds[1].id)
                        )
            return None
        except Exception:
            return None
