import pytest, respx, httpx
from polyedge.fetchers.polymarket import PolymarketFetcher

MOCK = [
    {
        "id": "evt-nba",
        "slug": "nba-lakers-vs-warriors",
        "ticker": "nba-lakers-warriors",
        "startDate": "2026-04-10T18:00:00Z",
        "tags": [{"label": "Sports", "slug": "sports"}, {"label": "NBA", "slug": "nba"}],
        "markets": [
            {
                "id": "0xabc",
                "question": "Will the Lakers beat the Warriors on April 10?",
                "endDate": "2026-04-11T04:00:00Z",
                "outcomePrices": "[\"0.65\", \"0.35\"]",
                "tokens": [{"token_id": "111", "outcome": "Yes"}, {"token_id": "222", "outcome": "No"}],
            }
        ],
    },
    {
        "id": "evt-nhl",
        "slug": "nhl-canadiens-vs-leafs",
        "ticker": "nhl-canadiens-leafs",
        "startDate": "2026-04-11T19:00:00Z",
        "tags": [{"label": "Sports", "slug": "sports"}, {"label": "NHL", "slug": "nhl"}],
        "markets": [
            {
                "id": "0xdef",
                "question": "Will the Canadiens beat the Leafs on April 11?",
                "endDate": "2026-04-12T03:00:00Z",
                "outcomePrices": "[\"0.55\", \"0.45\"]",
                "tokens": [{"token_id": "333", "outcome": "Yes"}, {"token_id": "444", "outcome": "No"}],
            }
        ],
    },
    {
        "id": "evt-crypto",
        "slug": "crypto-btc-price",
        "ticker": "crypto-btc",
        "startDate": "2026-04-12T00:00:00Z",
        "tags": [{"label": "Crypto", "slug": "crypto"}],
        "markets": [
            {
                "id": "0xpol",
                "question": "Will crypto go up?",
                "endDate": "2026-04-13T00:00:00Z",
                "outcomePrices": "[\"0.70\", \"0.30\"]",
                "tokens": [{"token_id": "555", "outcome": "Yes"}, {"token_id": "666", "outcome": "No"}],
            }
        ],
    },
]

@pytest.mark.asyncio
async def test_sports_only():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/events").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba", "nhl"])
    assert len(markets) == 2
    assert {m.sport for m in markets} == {"nba", "nhl"}

@pytest.mark.asyncio
async def test_prices_parsed():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/events").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba"])
    nba = markets[0]
    assert nba.price_yes == pytest.approx(0.65)
    assert nba.token_id_yes == "111"

@pytest.mark.asyncio
async def test_teams_extracted():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/events").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba"])
    nba = markets[0]
    assert nba.team_yes == "Lakers"
    assert nba.team_no == "Warriors"
