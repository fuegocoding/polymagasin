from __future__ import annotations
import os
import tomllib
from dataclasses import dataclass


@dataclass
class ScannerConfig:
    edge_threshold: float = 0.05
    scan_interval_minutes: int = 1
    stale_odds_minutes: int = 5
    bankroll: float = 1000.0


@dataclass
class Config:
    scanner: ScannerConfig
    sports: list[str]
    sources: dict[str, bool]
    db_path: str
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
    scanner = ScannerConfig(
        edge_threshold=float(os.getenv("EDGE_THRESHOLD", raw.get("edge_threshold", 0.01))),
        scan_interval_minutes=int(os.getenv("SCAN_INTERVAL_MINUTES", raw.get("scan_interval_minutes", 1))),
        stale_odds_minutes=int(os.getenv("STALE_ODDS_MINUTES", raw.get("stale_odds_minutes", 5))),
        bankroll=float(os.getenv("BANKROLL", raw.get("bankroll", 1000.0))),
    )
    db_path = os.getenv("DB_PATH", data.get("db", {}).get("path", "polyedge.db"))
    return Config(
        scanner=scanner,
        sports=data.get("sports", {}).get("enabled", ["nba", "nhl", "mlb", "epl"]),
        sources=data.get("sources", {"pinnacle": True, "stake": True, "miseonjeu": True}),
        db_path=db_path,
        pinnacle_api_key=os.getenv("PINNACLE_API_KEY", data.get("keys", {}).get("pinnacle_api_key", "")),
        stake_api_key=os.getenv("STAKE_API_KEY", data.get("keys", {}).get("stake_api_key", "")),
        miseonjeu_api_key=os.getenv("MISEONJEU_API_KEY", data.get("keys", {}).get("miseonjeu_api_key", "")),
        polymarket_key=os.getenv("POLYMARKET_KEY", data.get("keys", {}).get("polymarket_key", "")),
    )
