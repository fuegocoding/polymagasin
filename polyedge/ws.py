import asyncio
import json
from typing import Callable, Any, Coroutine
from rich.console import Console

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
        on_update: Callable[[dict, dict], Coroutine[Any, Any, None]],
    ):
        self.config = config
        self.db_conn = db_conn
        self.on_update = on_update
        self.markets = {}  # Market ID -> PolyMarket
        self.odds = {}  # (Source, Match ID) -> OddsLine
        self._tasks = []

    async def start(self):
        console.print("[cyan]Starting WebSocket Manager...[/cyan]")
        # Placeholder for starting actual WS connections
        # self._tasks.append(asyncio.create_task(self._connect_polymarket()))
        # self._tasks.append(asyncio.create_task(self._connect_stake()))

        # Simulate an update loop
        self._tasks.append(asyncio.create_task(self._dummy_loop()))
        await asyncio.gather(*self._tasks)

    async def _dummy_loop(self):
        while True:
            # wait for updates...
            await asyncio.sleep(5)
            # call the callback if state changed
            await self.on_update(list(self.markets.values()), list(self.odds.values()))

    def stop(self):
        for task in self._tasks:
            task.cancel()
