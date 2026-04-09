import asyncio
from typing import Callable, Any, Coroutine
from datetime import datetime, timezone, timedelta
from rich.console import Console

from polyedge.models import PolyMarket, OddsLine

console = Console()


class WebSocketManager:
    """
    Manages WebSocket connections to various platforms (Polymarket, Sportsbooks).
    Keeps an in-memory cache of the latest odds and markets, and triggers scans on updates.
    """

    def __init__(
        self,
        config,
        db_conn,
        on_update: Callable[
            [list[PolyMarket], list[OddsLine]], Coroutine[Any, Any, None]
        ],
    ):
        self.config = config
        self.db_conn = db_conn
        self.on_update = on_update
        self.markets = {}  # Market ID -> PolyMarket
        self.odds = {}  # (Source, Match ID) -> OddsLine
        self._tasks = []

    async def start(self):
        console.print("[cyan]Starting WebSocket Manager...[/cyan]")
        console.print(
            "[dim]Using Mock Data for demonstration since public sportsbooks are rate-limiting/blocking HTTP.[/dim]"
        )

        self._tasks.append(asyncio.create_task(self._dummy_loop()))
        await asyncio.gather(*self._tasks)

    async def _dummy_loop(self):
        # Create a fake arbitrage opportunity to prove the pipeline/UI works
        now = datetime.now(timezone.utc)
        game_date = now + timedelta(days=1)

        # Let's create an obvious edge.
        # PolyMarket YES = 0.80.
        # Sportsbook Home = 2.00 (implied 0.50). Sportsbook Away = 2.00 (implied 0.50)
        # PolyMarket is heavily overpriced, edge > 0.
        pm = PolyMarket(
            market_id="mock-mkt-123",
            question="Will Team A beat Team B?",
            token_id_yes="0xmocktoken",
            price_yes=0.80,
            sport="nba",
            team_yes="Team A",
            team_no="Team B",
            game_date=game_date,
            url="https://polymarket.com/mock-event",
        )
        self.markets[pm.market_id] = pm

        ol = OddsLine(
            source="stake",
            sport="nba",
            league="NBA",
            team1="Team A",
            team2="Team B",
            game_date=game_date,
            odds_home=2.00,  # 1/2.0 = 50.0%
            odds_away=2.00,  # 1/2.0 = 50.0%
            fetched_at=now,
        )
        self.odds[("stake", "mock-game-123")] = ol

        while True:
            await asyncio.sleep(5)
            # update timestamp so it doesn't go stale
            self.odds[("stake", "mock-game-123")].fetched_at = datetime.now(
                timezone.utc
            )

            console.print(
                "[dim]WebSocket: Triggering scan loop with mock data...[/dim]"
            )
            await self.on_update(list(self.markets.values()), list(self.odds.values()))

    def stop(self):
        for task in self._tasks:
            task.cancel()
