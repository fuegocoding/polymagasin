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
        self.api_key = api_key 

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        if not self.api_key:
            return []
            
        out = []
        try:
            # We must be careful: StakeAPI might use its own internal session
            # If we get 403s on Railway, it's likely IP blocking by Cloudflare
            async with StakeAPI(access_token=self.api_key) as client:
                for sport in sports:
                    try:
                        # Attempt to get events
                        events = await client.get_sports_events(sport=sport)
                        for ev in events:
                            line = self._parse_event(ev, sport)
                            if line:
                                out.append(line)
                    except Exception as se:
                        if "403" in str(se):
                            # Don't spam logs if we know we are blocked
                            pass
                        else:
                            print(f"[stake:fetch] Error for {sport}: {se}")
        except Exception as e:
            if "403" not in str(e):
                print(f"[stake:fetch] Global Error: {e}")
        return out

    def _parse_event(self, ev, sport) -> OddsLine | None:
        try:
            # Inspection of likely StakeAPI model attributes
            home = getattr(ev, 'home_team', None)
            away = getattr(ev, 'away_team', None)
            if not home or not away: return None
            
            home_name = home.name
            away_name = away.name
            
            markets = getattr(ev, 'markets', [])
            for market in markets:
                # Target the primary winner market
                if market.name.lower() in ("moneyline", "match winner", "1x2"):
                    selections = market.selections
                    if len(selections) >= 2:
                        return OddsLine(
                            source="stake",
                            sport=sport,
                            league=getattr(ev.league, 'name', sport.upper()) if hasattr(ev, 'league') else sport.upper(),
                            team1=normalize_team(home_name, sport),
                            team2=normalize_team(away_name, sport),
                            game_date=getattr(ev, 'start_time', datetime.now(timezone.utc)),
                            odds_home=selections[0].price,
                            odds_away=selections[1].price,
                            fetched_at=datetime.now(timezone.utc),
                            external_id=str(ev.id),
                            selection_id_home=str(selections[0].id),
                            selection_id_away=str(selections[1].id)
                        )
            return None
        except Exception:
            return None
