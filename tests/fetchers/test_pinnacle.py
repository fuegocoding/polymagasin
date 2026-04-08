import pytest, respx, httpx
from polyedge.fetchers.pinnacle import PinnacleFetcher

MOCK = {"matchups": [
    {"id": 1, "startTime": "2026-04-10T18:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Los Angeles Lakers", "alignment": "home"},
                      {"name": "Golden State Warriors", "alignment": "away"}],
     "periods": [{"number": 0, "moneyline": {"home": 1.85, "away": 2.10}}]},
    {"id": 2, "startTime": "2026-04-11T19:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Boston Celtics", "alignment": "home"},
                      {"name": "Miami Heat", "alignment": "away"}],
     "periods": [{"number": 0, "moneyline": {"home": 1.40, "away": 3.10}}]},
    {"id": 3, "startTime": "2026-04-10T20:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Dallas Mavericks", "alignment": "home"},
                      {"name": "Denver Nuggets", "alignment": "away"}],
     "periods": [{"number": 0}]},  # no moneyline — skip
]}

@pytest.mark.asyncio
async def test_returns_lines():
    with respx.mock:
        respx.get("https://www.pinnacle.com/api/v3/matchups").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "pinnacle" for l in lines)

@pytest.mark.asyncio
async def test_normalizes_teams():
    with respx.mock:
        respx.get("https://www.pinnacle.com/api/v3/matchups").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    assert g.odds_home == pytest.approx(1.85)