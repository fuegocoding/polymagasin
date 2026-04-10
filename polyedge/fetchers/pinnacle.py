from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

_BASE = "https://guest.api.arcadia.pinnacle.com/0.1"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
_LEAGUES: dict[str, list[int]] = {
    "nba": [487],
    "nhl": [1456],
    "mlb": [246],
    "epl": [1980],
}


def _to_decimal(american: float) -> float:
    if american > 0:
        return round(american / 100.0 + 1.0, 4)
    return round(100.0 / abs(american) + 1.0, 4)


class PinnacleFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        tasks = []
        sport_for_lid: dict[int, str] = {}
        for s in sports:
            for lid in _LEAGUES.get(s.lower(), []):
                sport_for_lid[lid] = s.lower()
                tasks.append(self._fetch_league(lid))
        if not tasks:
            return []
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = []
        for lid, res in zip(sport_for_lid.keys(), results):
            if isinstance(res, Exception):
                print(f"[pinnacle] league {lid} error: {res}")
            else:
                sport = sport_for_lid[lid]
                out.extend(self._parse_league(res[0], res[1], sport))
        return out

    async def _fetch_league(self, league_id: int):
        matchups, markets = await asyncio.gather(
            self._get_json(f"{_BASE}/leagues/{league_id}/matchups", headers=_HEADERS),
            self._get_json(f"{_BASE}/leagues/{league_id}/markets/straight", headers=_HEADERS),
        )
        return matchups, markets

    def _parse_league(self, matchups: list, markets: list, sport: str) -> list[OddsLine]:
        # Build moneyline index (period 0, not alternate) keyed by matchupId
        ml: dict[int, dict] = {}
        for m in markets:
            if m.get("type") == "moneyline" and m.get("period") == 0 and not m.get("isAlternate"):
                ml[m["matchupId"]] = m

        lines = []
        for mu in matchups:
            mid = mu.get("id")
            if mid not in ml:
                continue
            parts = mu.get("participants", [])
            home = next((p["name"] for p in parts if p.get("alignment") == "home"), None)
            away = next((p["name"] for p in parts if p.get("alignment") == "away"), None)
            if not home or not away:
                continue
            try:
                gd = datetime.fromisoformat(mu["startTime"].replace("Z", "+00:00"))
            except Exception:
                continue
            prices = ml[mid].get("prices", [])
            h_sel = next((p for p in prices if p.get("designation") == "home"), None)
            a_sel = next((p for p in prices if p.get("designation") == "away"), None)
            if h_sel is None or a_sel is None:
                continue
            
            hp, ap = h_sel["price"], a_sel["price"]
            league_name = mu.get("league", {}).get("name", sport.upper())
            
            lines.append(OddsLine(
                source="pinnacle", 
                sport=sport, 
                league=league_name,
                team1=normalize_team(home, sport),
                team2=normalize_team(away, sport),
                game_date=gd,
                odds_home=_to_decimal(hp),
                odds_away=_to_decimal(ap),
                fetched_at=datetime.now(timezone.utc),
                external_id=str(mid),
                selection_id_home=str(h_sel.get("lineId") or mid),
                selection_id_away=str(a_sel.get("lineId") or mid)
            ))
        return lines
