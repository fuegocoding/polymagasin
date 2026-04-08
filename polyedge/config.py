from __future__ import annotations
import tomllib
from dataclasses import dataclass

@dataclass
class ScannerConfig:
    edge_threshold: float = 0.05
    scan_interval_minutes: int = 30
    stale_odds_minutes: int = 30
    bankroll: float = 500.0

@dataclass
class Config:
    scanner: ScannerConfig
    sports: list[str]
    sources: dict[str, bool]
    db_path: str
    stake_api_key: str = ""

def load_config(path: str = "config.toml") -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    raw = data.get("scanner", {})
    scanner = ScannerConfig(
        edge_threshold=raw.get("edge_threshold", 0.05),
        scan_interval_minutes=raw.get("scan_interval_minutes", 30),
        stale_odds_minutes=raw.get("stale_odds_minutes", 30),
        bankroll=raw.get("bankroll", 500.0),
    )
    return Config(
        scanner=scanner,
        sports=data.get("sports", {}).get("enabled", ["nba", "nhl", "mlb", "epl"]),
        sources=data.get("sources", {"pinnacle": True, "stake": True, "miseonjeu": True}),
        db_path=data.get("db", {}).get("path", "polyedge.db"),
        stake_api_key=data.get("keys", {}).get("stake_api_key", ""),
    )