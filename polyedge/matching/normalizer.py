from __future__ import annotations
import json
from pathlib import Path

_ALIASES_PATH = Path(__file__).parent / "aliases.json"
with open(_ALIASES_PATH) as f:
    _ALIASES: dict[str, dict[str, str]] = json.load(f)

_LOWER: dict[str, dict[str, str]] = {
    sport: {k.lower(): v for k, v in mapping.items()}
    for sport, mapping in _ALIASES.items()
}

def normalize_team(name: str, sport: str) -> str:
    return _LOWER.get(sport.lower(), {}).get(name.lower(), name)