from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from rapidfuzz import fuzz
from polyedge.models import OddsLine, PolyMarket
from polyedge.matching.normalizer import normalize_team

_WINDOW = timedelta(hours=4)
_FUZZ_MIN = 85

@dataclass
class MatchResult:
    matched_lines: list[OddsLine]
    team_is_home: bool

def find_matching_odds(poly: PolyMarket, lines: list[OddsLine]) -> MatchResult | None:
    cy = normalize_team(poly.team_yes, poly.sport)
    cn = normalize_team(poly.team_no, poly.sport)
    matched, is_home = [], None
    for line in lines:
        if line.sport.lower() != poly.sport.lower():
            continue
        if abs(line.game_date - poly.game_date) > _WINDOW:
            continue
        c1 = normalize_team(line.team1, line.sport)
        c2 = normalize_team(line.team2, line.sport)
        ok, h = _match(cy, cn, c1, c2)
        if ok:
            matched.append(line)
            is_home = h
    return MatchResult(matched, is_home) if matched else None

def _match(yes, no, t1, t2):
    if yes == t1 and no == t2: return True, True
    if yes == t2 and no == t1: return True, False
    sh = min(fuzz.token_sort_ratio(yes, t1), fuzz.token_sort_ratio(no, t2))
    sa = min(fuzz.token_sort_ratio(yes, t2), fuzz.token_sort_ratio(no, t1))
    if sh >= _FUZZ_MIN and sh >= sa: return True, True
    if sa >= _FUZZ_MIN: return True, False
    return False, False