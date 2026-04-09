import asyncio
import httpx
from typing import Callable, Any, Coroutine
from datetime import datetime, timezone, timedelta
from rich.console import Console

from polyedge.models import PolyMarket, OddsLine
from polyedge.fetchers.polymarket import PolymarketFetcher
from polyedge.fetchers.pinnacle import PinnacleFetcher
from polyedge.fetchers.stake import StakeFetcher
from polyedge.fetchers.miseonjeu import MiseonjeuFetcher

console = Console()


class WebSocketManager:
    """
    Manages real-time data ingestion. Connects to the configured sportsbooks
    and Polymarket to stream active prices.
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
        self._managed_tasks: dict[str, asyncio.Task] = {}
        self._client = None
        self._debounce_task: asyncio.Task | None = None

    async def start(self):
        console.print("[cyan]Starting Real-Time Data Manager...[/cyan]")
        self._client = httpx.AsyncClient(
            headers={"User-Agent": "PolyEdge/1.0"}, follow_redirects=True
        )

        # Start Polymarket permanently
        self._tasks.append(asyncio.create_task(self._poll_polymarket()))

        while True:
            # Check for config changes periodically
            from polyedge.config import load_config
            try:
                # Reload config to detect source toggles from UI
                self.config = load_config()
            except Exception: pass
            
            active_sources = [k for k, v in self.config.sources.items() if v]
            
            # Start new tasks if enabled in config but not running
            if "pinnacle" in active_sources and "pinnacle" not in self._managed_tasks:
                self._managed_tasks["pinnacle"] = asyncio.create_task(
                    self._poll_sportsbook("pinnacle", PinnacleFetcher, self.config.pinnacle_api_key)
                )
            if "stake" in active_sources and "stake" not in self._managed_tasks:
                self._managed_tasks["stake"] = asyncio.create_task(
                    self._poll_sportsbook("stake", StakeFetcher, self.config.stake_api_key)
                )
            if "miseonjeu" in active_sources and "miseonjeu" not in self._managed_tasks:
                self._managed_tasks["miseonjeu"] = asyncio.create_task(
                    self._poll_sportsbook("miseonjeu", MiseonjeuFetcher, self.config.miseonjeu_api_key)
                )
                
            # Cancel tasks if disabled in config but currently running
            to_stop = [name for name in self._managed_tasks if name not in active_sources]
            for name in to_stop:
                console.print(f"[yellow][system] Stopping source: {name}[/yellow]")
                self._managed_tasks[name].cancel()
                del self._managed_tasks[name]
                # Cleanup related odds to prevent stale arb detection
                self.odds = {k: v for k, v in self.odds.items() if k[0] != name}

            await asyncio.sleep(10) # check for config changes every 10s

    async def _poll_polymarket(self):
        fetcher = PolymarketFetcher(self._client)
        while True:
            try:
                markets = await fetcher.fetch(self.config.sports)
                self.markets = {m.market_id: m for m in markets}
                console.print(f"[cyan][Polymarket] {len(markets)} active markets[/cyan]")
                await self._trigger_update()
            except Exception as e:
                console.print(f"[red][Polymarket] Error: {e}[/red]")
            await asyncio.sleep(self.config.scanner.scan_interval_minutes * 60)

    async def _poll_sportsbook(self, name, fetcher_cls, api_key):
        # Stagger start to avoid spikes
        import random as _random
        await asyncio.sleep(_random.uniform(2, 10))
        fetcher = fetcher_cls(self._client, api_key)
        while True:
            try:
                lines = await fetcher.fetch(self.config.sports)
                for l in lines:
                    key = (name, l.sport, l.team1, l.team2, l.game_date.date())
                    self.odds[key] = l
                console.print(f"[cyan][{name}] {len(lines)} odds lines[/cyan]")
                await self._trigger_update()
            except Exception as e:
                console.print(f"[red][{name}] Error: {e}[/red]")
            await asyncio.sleep(self.config.scanner.scan_interval_minutes * 60)

    async def _trigger_update(self):
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()
        try:
            self._debounce_task = asyncio.create_task(self._delayed_update())
        except Exception: pass

    async def _delayed_update(self):
        try:
            await asyncio.sleep(5)  # wait 5s to batch updates
            if self.markets:
                await self.on_update(list(self.markets.values()), list(self.odds.values()))
        except asyncio.CancelledError:
            pass
        except Exception as e:
            console.print(f"[red][Update Error] {e}[/red]")
            import traceback
            traceback.print_exc()

    def stop(self):
        for task in self._tasks:
            task.cancel()
        for task in self._managed_tasks.values():
            task.cancel()
        if self._client:
            asyncio.create_task(self._client.aclose())
