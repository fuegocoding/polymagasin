from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
import httpx
from polyedge.models import OddsLine

class BaseFetcher(ABC):
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def fetch(self, sports: list[str]) -> list[OddsLine]: ...

    async def _get_json(self, url: str, **kwargs) -> list | dict:
        last = None
        for i in range(3):
            try:
                r = await self.client.get(url, timeout=15.0, **kwargs)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                if i < 2: await asyncio.sleep(2 ** i)
        raise last