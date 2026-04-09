from __future__ import annotations
import asyncio, json as _json, re
from datetime import datetime, timezone
import httpx
from polyedge.models import PolyMarket
from polyedge.matching.normalizer import normalize_team

_BASE = "https://gamma-api.polymarket.com"
_WILL_BEAT = re.compile(
    r"Will (?:the )?(.+?) (?:beat|defeat|win (?:vs?\.?|against)) (?:the )?(.+?)(?:\s+by|\s+on\b|\?|$)",
    re.IGNORECASE,
)
_VS = re.compile(r"^(.+?)\s+vs\.?\s+(.+?)(?:\s*[-–]|\?|$)", re.IGNORECASE)


class PolymarketFetcher:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self, sports: list[str]) -> list[PolyMarket]:
        events = await self._fetch_all_events()
        from rich.console import Console as _C; _c = _C()
        _c.print(f"[dim][Polymarket] {len(events)} total events fetched[/dim]")
        markets = []
        for sport in sports:
            sport_matches = 0
            for event in events:
                ticker = event.get("ticker", "").lower()
                slug = event.get("slug", "").lower()

                is_match = False
                if ticker.startswith(f"{sport}-") or slug.startswith(f"{sport}-"):
                    is_match = True

                if not is_match:
                    tags = [t.get("slug", "").lower() for t in event.get("tags", [])]
                    if sport in tags:
                        is_match = True

                if not is_match:
                    continue

                sport_matches += 1
                for market in event.get("markets", []):
                    p = self._parse(event, market, sport)
                    if p:
                        markets.append(p)
            _c.print(f"[dim][Polymarket] {sport}: {sport_matches} events matched[/dim]")
        return markets

    async def _fetch_all_events(self) -> list[dict]:
        all_events = []
        offset = 0
        limit = 500
        while True:
            data = await self._get(
                f"{_BASE}/events",
                params={
                    "active": "true",
                    "closed": "false",
                    "limit": limit,
                    "offset": offset,
                },
            )
            if not data:
                break
            all_events.extend(data)
            if len(data) < limit:
                break
            offset += limit
        return all_events

    def _parse(self, event, market, sport) -> PolyMarket | None:
        try:
            prices = market.get("outcomePrices", '["0.5","0.5"]')
            if isinstance(prices, str):
                prices = _json.loads(prices)
            price_yes = float(prices[0])
        except Exception:
            return None

        q = market.get("question", "")
        # Filter out O/U, spreads, etc.
        q_lower = q.lower()
        if "o/u" in q_lower or "spread" in q_lower or ":" in q:
            return None

        # Look for tokens array, otherwise construct a dummy id for paper trading
        tokens = market.get("tokens", [])
        if tokens:
            tid = next(
                (t["token_id"] for t in tokens if t.get("outcome", "") == "Yes"),
                tokens[0].get("token_id"),
            )
        else:
            tid = market.get("conditionId", "unknown")

        if not tid:
            return None

        q = market.get("question", "")
        ty, tn = self._teams(q, sport)
        if not ty or not tn:
            return None
        try:
            # use end date or start date as game date approximation from the parent event
            date_str = market.get("endDate") or event.get("startDate") or ""
            gd = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None

        slug = event.get("slug", event.get("id", ""))
        return PolyMarket(
            market["id"],
            q,
            tid,
            price_yes,
            sport,
            normalize_team(ty, sport),
            normalize_team(tn, sport),
            gd,
            f"https://polymarket.com/event/{slug}",
        )

    def _teams(self, q, sport):
        m = _WILL_BEAT.search(q)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        m = _VS.search(q)
        if m:
            return m.group(1).strip(), m.group(2).strip()
        return None, None

    async def _get(self, url, **kw):
        last = None
        for i in range(3):
            try:
                r = await self.client.get(url, timeout=15.0, **kw)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                if i < 2:
                    await asyncio.sleep(2**i)
        if last is not None:
            raise last
        raise Exception("Request failed")
