from __future__ import annotations
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

_BASE = "https://www.pinnacle.com/api/v3"
_LEAGUES: dict[str, list[int]] = {
    "nba": [487],
    "nhl": [1456],
    "mlb": [246],
    "epl": [1980],
}


class PinnacleFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        ids, by_lid = [], {}
        for s in sports:
            for lid in _LEAGUES.get(s.lower(), []):
                ids.append(lid)
                by_lid[lid] = s.lower()
        if not ids:
            return []

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Basic {self.api_key}"

        data = await self._get_json(
            f"{_BASE}/matchups",
            params={
                "leagueIds": ",".join(str(i) for i in ids),
                "withSpecials": "false",
                "brandId": "1",
            },
            headers=headers,
        )
        return [
            l for m in data.get("matchups", []) for l in [self._parse(m, by_lid)] if l
        ]

    def _parse(self, m, by_lid) -> OddsLine | None:
        sport = by_lid.get(m.get("league", {}).get("id"))
        if not sport:
            return None
        ml = next(
            (
                p["moneyline"]
                for p in m.get("periods", [])
                if p.get("number") == 0 and "moneyline" in p
            ),
            None,
        )
        if not ml:
            return None
        parts = m.get("participants", [])
        home = next((p["name"] for p in parts if p.get("alignment") == "home"), None)
        away = next((p["name"] for p in parts if p.get("alignment") == "away"), None)
        if not home or not away:
            return None
        try:
            gd = datetime.fromisoformat(m["startTime"].replace("Z", "+00:00"))
        except Exception:
            return None
        return OddsLine(
            "pinnacle",
            sport,
            m.get("league", {}).get("name", sport.upper()),
            normalize_team(home, sport),
            normalize_team(away, sport),
            gd,
            float(ml["home"]),
            float(ml["away"]),
            datetime.now(timezone.utc),
        )
