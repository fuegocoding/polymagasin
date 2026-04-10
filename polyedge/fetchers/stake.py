from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

_URLS = [
    "https://api.stake.com/graphql",
    "https://stake.com/_api/graphql",
]
_SLUGS = {
    "basketball_nba": "nba",
    "ice_hockey_nhl": "nhl",
    "baseball_mlb": "mlb",
    "soccer_england_premier_league": "epl",
}
_QUERY = """
query SportsbookEventList($sportSlug: String!, $limit: Int) {
  sportsbookEventList(sportSlug: $sportSlug, limit: $limit, status: UPCOMING) {
    id name startTime sport { slug }
    markets(name: "Match Winner") { id name outcomes { id name price } }
  }
}"""


class StakeFetcher(BaseFetcher):
    def __init__(self, client: httpx.AsyncClient, api_key: str = ""):
        super().__init__(client)
        self.api_key = api_key

    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        rev = {v: k for k, v in _SLUGS.items()}
        results = await asyncio.gather(
            *[self._sport(s, rev[s]) for s in sports if s in rev],
            return_exceptions=True,
        )
        out = []
        for r in results:
            if isinstance(r, Exception):
                print(f"[stake] {r}")
            else:
                out.extend(r)
        return out

    async def _sport(self, sport, slug) -> list[OddsLine]:
        last = None
        for i in range(3):
            try:
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Origin": "https://stake.com",
                    "Referer": "https://stake.com/",
                    "Accept": "application/json",
                }
                if self.api_key:
                    headers["x-access-token"] = self.api_key
                    headers["Authorization"] = f"Bearer {self.api_key}"
                payload = {
                    "operationName": "SportsbookEventList",
                    "query": _QUERY,
                    "variables": {"sportSlug": slug, "limit": 200},
                }
                for url in _URLS:
                    try:
                        r = await self.client.post(
                            url,
                            json=payload,
                            timeout=15.0,
                            headers=headers,
                        )
                        r.raise_for_status()
                        evs = r.json().get("data", {}).get("sportsbookEventList", [])
                        if isinstance(evs, list):
                            return [l for e in evs for l in [self._parse(e, sport)] if l]
                    except Exception as e:
                        last = e
                        continue
                raise last if last else RuntimeError("stake fetch failed")
            except Exception as e:
                last = e
                if i < 2:
                    await asyncio.sleep(2**i)
        raise last

    def _parse(self, ev, sport) -> OddsLine | None:
        mkt = next(
            (m for m in ev.get("markets", []) if "winner" in m.get("name", "").lower()),
            None,
        )
        if not mkt:
            return None
        outs = mkt.get("outcomes", [])
        if len(outs) < 2:
            return None
        name = ev.get("name", "")
        parts = [p.strip() for p in name.split(" vs ")]
        rh, ra = (
            (parts[0], parts[1])
            if len(parts) == 2
            else (outs[0]["name"], outs[1]["name"])
        )
        try:
            gd = datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
        except Exception:
            return None
        return OddsLine(
            "stake",
            sport,
            sport.upper(),
            normalize_team(rh, sport),
            normalize_team(ra, sport),
            gd,
            float(outs[0]["price"]),
            float(outs[1]["price"]),
            datetime.now(timezone.utc),
            str(mkt.get("id")) if mkt.get("id") is not None else None,
            str(outs[0].get("id")) if outs[0].get("id") is not None else None,
            str(outs[1].get("id")) if outs[1].get("id") is not None else None,
        )
