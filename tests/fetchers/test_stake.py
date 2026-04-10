import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
from polyedge.fetchers.stake import StakeFetcher

# Raw GraphQL data that StakeAPI._graphql_request returns (the "data" layer unwrapped)
GRAPHQL_DATA = {"sportsbookEventList": [
    {"id": "s1", "name": "Los Angeles Lakers vs Golden State Warriors",
     "startTime": "2026-04-10T18:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"id": "m1", "name": "Match Winner",
                  "outcomes": [{"id": "o1", "name": "Los Angeles Lakers", "price": 1.85},
                               {"id": "o2", "name": "Golden State Warriors", "price": 2.10}]}]},
    {"id": "s2", "name": "Boston Celtics vs Miami Heat",
     "startTime": "2026-04-11T19:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"id": "m2", "name": "Match Winner",
                  "outcomes": [{"id": "o3", "name": "Boston Celtics", "price": 1.40},
                               {"id": "o4", "name": "Miami Heat", "price": 3.10}]}]},
]}


def _make_stake_api_mock(return_value):
    """Return a patched StakeAPI context manager whose _graphql_request returns return_value."""
    mock_client = AsyncMock()
    mock_client._graphql_request = AsyncMock(return_value=return_value)

    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_cm


@pytest.mark.asyncio
async def test_returns_lines():
    with patch("polyedge.fetchers.stake.StakeAPI", return_value=_make_stake_api_mock(GRAPHQL_DATA)):
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "stake" for l in lines)


@pytest.mark.asyncio
async def test_correct_odds():
    with patch("polyedge.fetchers.stake.StakeAPI", return_value=_make_stake_api_mock(GRAPHQL_DATA)):
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    assert g.odds_home == pytest.approx(1.85)
    assert g.market_id == "m1"
    assert g.home_outcome_id == "o1"
    assert g.away_outcome_id == "o2"


@pytest.mark.asyncio
async def test_api_key_forwarded_to_stakeapi():
    """Ensure the access_token is passed to StakeAPI when a key is provided."""
    call_args = {}

    def capture_init(**kwargs):
        call_args.update(kwargs)
        return _make_stake_api_mock(GRAPHQL_DATA)

    with patch("polyedge.fetchers.stake.StakeAPI", side_effect=capture_init):
        async with httpx.AsyncClient() as c:
            await StakeFetcher(c, api_key="my-test-key").fetch(["nba"])

    assert call_args.get("access_token") == "my-test-key"
