from __future__ import annotations
import asyncio, json as _json, re
from datetime import datetime, timezone
import httpx
from polyedge.models import PolyMarket
from polyedge.matching.normalizer import normalize_team

_BASE = "https://gamma-api.polymarket.com"
_WILL_BEAT = re.compile(
    r"Will (?:the )?(.+?) (?:beat|defeat|win (?:vs?\.?|against)) (?:the )?(.+?)(?:\s+on\b|\?|$)",
    re.IGNORECASE)
_VS = re.compile(r"^(.+?)\s+vs\.?\s+(.+?)(?:\s*[-–]|\?|$)", re.IGNORECASE)

class PolymarketFetcher:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self, sports: list[str]) -> list[PolyMarket]:
        data = await self._get(f"{_BASE}/markets",
                               params={"active": "true", "closed": "false", "limit": 500})
        return [m for item in data for m in [self._parse(item, sports)] if m]

    def _parse(self, item, sports) -> PolyMarket | None:
        tags = [t.get("slug", "").lower() for t in item.get("tags", [])]
        sport = next((t for t in tags if t in sports), None)
        if not sport: return None
        try:
            prices = item.get("outcomePrices", '["0.5","0.5"]')
            price_yes = float((_json.loads(prices) if isinstance(prices, str) else prices)[0])
        except Exception: return None
        tokens = item.get("tokens", [])
        tid = next((t["token_id"] for t in tokens if t.get("outcome") == "Yes"), None)
        if not tid: return None
        ty, tn = self._teams(item.get("question", ""), sport)
        if not ty or not tn: return None
        try:
            gd = datetime.fromisoformat(item["startDate"].replace("Z", "+00:00"))
        except Exception: return None
        slug = item.get("slug", item.get("id", ""))
        return PolyMarket(item["id"], item.get("question",""), tid, price_yes, sport,
                          normalize_team(ty, sport), normalize_team(tn, sport),
                          gd, f"https://polymarket.com/event/{slug}")

    def _teams(self, q, sport):
        m = _WILL_BEAT.search(q)
        if m: return m.group(1).strip(), m.group(2).strip()
        m = _VS.search(q)
        if m: return m.group(1).strip(), m.group(2).strip()
        return None, None

    async def _get(self, url, **kw):
        last = None
        for i in range(3):
            try:
                r = await self.client.get(url, timeout=15.0, **kw)
                r.raise_for_status(); return r.json()
            except Exception as e:
                last = e
                if i < 2: await asyncio.sleep(2 ** i)
        raise last