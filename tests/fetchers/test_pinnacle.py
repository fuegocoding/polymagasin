import pytest, respx, httpx
from polyedge.fetchers.pinnacle import PinnacleFetcher

MOCK_MATCHUPS = [
    {
        "id": 1,
        "startTime": "2026-04-10T18:00:00Z",
        "league": {"id": 487, "name": "NBA"},
        "participants": [
            {"name": "Los Angeles Lakers", "alignment": "home"},
            {"name": "Golden State Warriors", "alignment": "away"},
        ],
        "periods": [{"period": 0, "hasMoneyline": True, "status": "open"}],
    },
    {
        "id": 2,
        "startTime": "2026-04-11T19:00:00Z",
        "league": {"id": 487, "name": "NBA"},
        "participants": [
            {"name": "Boston Celtics", "alignment": "home"},
            {"name": "Miami Heat", "alignment": "away"},
        ],
        "periods": [{"period": 0, "hasMoneyline": True, "status": "open"}],
    },
    {
        "id": 3,
        "startTime": "2026-04-10T20:00:00Z",
        "league": {"id": 487, "name": "NBA"},
        "participants": [
            {"name": "Dallas Mavericks", "alignment": "home"},
            {"name": "Denver Nuggets", "alignment": "away"},
        ],
        "periods": [{"period": 0, "hasMoneyline": False, "status": "open"}],
    },
]

# American odds: Lakers -118 (home underdog), Warriors -105
# Decimal: 100/118+1=1.847, 100/105+1=1.952... but let's use simpler values
# Lakers: -118 → 1.847, Warriors: +105 → 2.05
# Celtics: -250 → 1.40, Heat: +200 → 3.00
MOCK_MARKETS = [
    {
        "matchupId": 1,
        "type": "moneyline",
        "period": 0,
        "isAlternate": False,
        "prices": [
            {"designation": "home", "price": -118},  # Lakers → 1.847
            {"designation": "away", "price": 105},   # Warriors → 2.05
        ],
    },
    {
        "matchupId": 2,
        "type": "moneyline",
        "period": 0,
        "isAlternate": False,
        "prices": [
            {"designation": "home", "price": -250},  # Celtics → 1.40
            {"designation": "away", "price": 200},   # Heat → 3.00
        ],
    },
    # No moneyline for matchup 3
    {
        "matchupId": 3,
        "type": "spread",
        "period": 0,
        "isAlternate": False,
        "prices": [{"designation": "home", "price": -110}, {"designation": "away", "price": -110}],
    },
]


@pytest.mark.asyncio
async def test_returns_lines():
    with respx.mock:
        respx.get("https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/matchups").mock(
            return_value=httpx.Response(200, json=MOCK_MATCHUPS))
        respx.get("https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/markets/straight").mock(
            return_value=httpx.Response(200, json=MOCK_MARKETS))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "pinnacle" for l in lines)


@pytest.mark.asyncio
async def test_normalizes_teams():
    with respx.mock:
        respx.get("https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/matchups").mock(
            return_value=httpx.Response(200, json=MOCK_MATCHUPS))
        respx.get("https://guest.api.arcadia.pinnacle.com/0.1/leagues/487/markets/straight").mock(
            return_value=httpx.Response(200, json=MOCK_MARKETS))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    # -118 American → 100/118 + 1 = 1.8474...
    assert g.odds_home == pytest.approx(100 / 118 + 1, rel=1e-3)
    # +105 American → 105/100 + 1 = 2.05
    assert g.odds_away == pytest.approx(2.05, rel=1e-3)
