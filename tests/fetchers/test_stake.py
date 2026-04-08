import pytest, respx, httpx
from polyedge.fetchers.stake import StakeFetcher

MOCK = {"data": {"sportsbookEventList": [
    {"id": "s1", "name": "Los Angeles Lakers vs Golden State Warriors",
     "startTime": "2026-04-10T18:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"name": "Match Winner",
                  "outcomes": [{"name": "Los Angeles Lakers", "price": 1.85},
                               {"name": "Golden State Warriors", "price": 2.10}]}]},
    {"id": "s2", "name": "Boston Celtics vs Miami Heat",
     "startTime": "2026-04-11T19:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"name": "Match Winner",
                  "outcomes": [{"name": "Boston Celtics", "price": 1.40},
                               {"name": "Miami Heat", "price": 3.10}]}]},
]}}

@pytest.mark.asyncio
async def test_returns_lines():
    with respx.mock:
        respx.post("https://stake.com/_api/graphql").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "stake" for l in lines)

@pytest.mark.asyncio
async def test_correct_odds():
    with respx.mock:
        respx.post("https://stake.com/_api/graphql").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    assert g.odds_home == pytest.approx(1.85)