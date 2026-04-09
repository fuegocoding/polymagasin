from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

# Verify: open miseonjeu.com → DevTools → Network → filter kambicdn.com
# Look for the path segment after /v2018/ — update this if wrong
_CLIENT = "lqmiseonjeu"
_BASE = f"https://eu-offering-api.kambicdn.com/offering/v2018/{_CLIENT}"
_SPORTS = {
    "nba": "basketball/nba",
    "nhl": "ice_hockey/nhl",
    "mlb": "baseball/mlb",
    "epl": "football/england/premier_league",
}


class MiseonjeuFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        results = await asyncio.gather(
            *[self._sport(s) for s in sports if s in _SPORTS], return_exceptions=True
        )
        out = []
        for r in results:
            if isinstance(r, Exception):
                print(f"[miseonjeu] {r}")
            else:
                out.extend(r)
        return out

    async def _sport(self, sport) -> list[OddsLine]:
        path = _SPORTS[sport].replace("/", "_")
        url = f"{_BASE}/listView/{path}.json"
        for i in range(3):
            try:
                headers = {}
                if self.api_key:
                    headers["Authorization"] = f"Bearer {self.api_key}"
                # Sometimes user-agent helps bypass basic blocks if unauthenticated
                headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
                r = await self.client.get(
                    url,
                    params={"lang": "fr_CA", "market": "CA"},
                    timeout=15.0,
                    headers=headers,
                )
                r.raise_for_status()
                return self._parse_response(r.json(), sport)
            except Exception as e:
                if i == 2:
                    print(f"[miseonjeu] {sport} failed: {e}")
                    return []
                await asyncio.sleep(2**i)
        return []

    def _parse_response(self, data, sport) -> list[OddsLine]:
        return [
            l for ev in data.get("events", []) for l in [self._parse(ev, sport)] if l
        ]

    def _parse(self, ev, sport) -> OddsLine | None:
        try:
            ed = ev.get("event", ev)
            name = ed.get("name", "")
            if " - " not in name:
                return None
            home_raw, away_raw = name.split(" - ", 1)
            gd = datetime.fromisoformat(ed.get("start", "").replace("Z", "+00:00"))
            bet_offers = ed.get("betOffers", [])
            offer = next(
                (
                    b
                    for b in bet_offers
                    if b.get("betOfferType", {}).get("name", "")
                    in ("Match", "1X2", "Moneyline", "To Win")
                ),
                None,
            )
            if not offer:
                return None
            outs = offer.get("outcomes", [])
            ho = next(
                (o for o in outs if o.get("label") in ("1", "Home", home_raw.strip())),
                None,
            )
            ao = next(
                (o for o in outs if o.get("label") in ("2", "Away", away_raw.strip())),
                None,
            )
            if not ho or not ao:
                return None
            return OddsLine(
                "miseonjeu",
                sport,
                sport.upper(),
                normalize_team(home_raw.strip(), sport),
                normalize_team(away_raw.strip(), sport),
                gd,
                ho["odds"] / 1000.0,
                ao["odds"] / 1000.0,
                datetime.now(timezone.utc),
            )
        except Exception:
            return None
