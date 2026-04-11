from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass

# --- AIOHTTP PROXY MONKEY-PATCH FOR STAKEAPI ---
try:
    import aiohttp
    if not hasattr(aiohttp.ClientSession, "_patched_for_proxy"):
        _orig_request = aiohttp.ClientSession._request
        async def _proxy_request(self, method, str_or_url, **kwargs):
            proxy = os.getenv("STAKE_PROXY")
            if proxy and 'stake.com' in str(str_or_url) and 'proxy' not in kwargs:
                kwargs['proxy'] = proxy
            return await _orig_request(self, method, str_or_url, **kwargs)
        aiohttp.ClientSession._request = _proxy_request
        aiohttp.ClientSession._patched_for_proxy = True
except ImportError:
    pass
# -----------------------------------------------

@dataclass
class ScannerConfig:
    edge_threshold: float = 0.05
    scan_interval_minutes: int = 1
    stale_odds_minutes: int = 5
    bankroll: float = 1000.0
    execution_enabled: bool = False


@dataclass
class Config:
    scanner: ScannerConfig
    sports: list[str]
    sources: dict[str, bool]
    db_path: str
    database_url: str | None = None
    pinnacle_api_key: str = ""
    stake_api_key: str = ""
    miseonjeu_api_key: str = ""
    polymarket_key: str = ""


def load_config(path: str | None = None) -> Config:
    """Load config from TOML file, with environment variables taking precedence."""
    if path is None:
        path = os.getenv("CONFIG_PATH", "config.toml")

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        data = {}

    raw = data.get("scanner", {})
    
    # Environment variables are the primary source for all sensitive keys and toggles
    scanner = ScannerConfig(
        edge_threshold=float(os.getenv("EDGE_THRESHOLD", raw.get("edge_threshold", 0.01))),
        scan_interval_minutes=int(os.getenv("SCAN_INTERVAL_MINUTES", raw.get("scan_interval_minutes", 1))),
        stale_odds_minutes=int(os.getenv("STALE_ODDS_MINUTES", raw.get("stale_odds_minutes", 5))),
        bankroll=float(os.getenv("BANKROLL", raw.get("bankroll", 1000.0))),
        execution_enabled=os.getenv("EXECUTION_ENABLED", str(raw.get("execution_enabled", False))).lower() == "true",
    )
    
    db_path = os.getenv("DB_PATH", data.get("db", {}).get("path", "polyedge.db"))
    database_url = os.getenv("DATABASE_URL", data.get("db", {}).get("url"))
    
    # Provider toggles strictly from environment variables or defaults
    def is_enabled(name, default):
        env_val = os.getenv(f"ENABLE_{name.upper()}")
        if env_val is not None:
            return env_val.lower() == "true"
        return data.get("sources", {}).get(name, default)

    sources = {
        "pinnacle": is_enabled("pinnacle", True),
        "stake": is_enabled("stake", False),
        "miseonjeu": is_enabled("miseonjeu", False),
    }
    
    return Config(
        scanner=scanner,
        sports=data.get("sports", {}).get("enabled", ["nba", "nhl", "mlb", "epl"]),
        sources=sources,
        db_path=db_path,
        database_url=database_url,
        # Keys strictly from environment variables for security
        pinnacle_api_key=os.getenv("PINNACLE_API_KEY", ""),
        stake_api_key=os.getenv("STAKE_API_KEY", ""),
        miseonjeu_api_key=os.getenv("MISEONJEU_API_KEY", ""),
        polymarket_key=os.getenv("POLYMARKET_KEY", ""),
    )
