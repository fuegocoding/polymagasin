from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from stakeapi import StakeAPI
from stakeapi.exceptions import StakeAPIError
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

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

    async def _sport(self, sport: str, slug: str) -> list[OddsLine]:
        last: Exception | None = None
        for i in range(3):
            try:
                async with StakeAPI(access_token=self.api_key or None) as stake:
                    data = await stake._graphql_request(
                        _QUERY,
                        variables={"sportSlug": slug, "limit": 200},
                        operation_name="SportsbookEventList",
                    )
                evs = data.get("sportsbookEventList") or []
                return [line for e in evs for line in [self._parse(e, sport)] if line]
            except StakeAPIError as e:
                last = e
                if i < 2:
                    await asyncio.sleep(2**i)
            except Exception as e:
                last = e
                if i < 2:
                    await asyncio.sleep(2**i)
        if last is not None:
            raise last
        raise RuntimeError("stake fetch failed")

    def _parse(self, ev: dict, sport: str) -> OddsLine | None:
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
