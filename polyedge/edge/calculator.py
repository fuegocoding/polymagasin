from __future__ import annotations
from dataclasses import dataclass

@dataclass
class EdgeResult:
    edge_pct: float
    fair_value: float

def implied_prob(decimal_odds: float) -> float:
    return 1.0 / decimal_odds

def devig(odds_home: float, odds_away: float) -> tuple[float, float]:
    rh, ra = implied_prob(odds_home), implied_prob(odds_away)
    o = rh + ra
    return rh / o, ra / o

def calculate_edge(poly_price, fair_home, fair_away, team_is_home) -> EdgeResult | None:
    fv = fair_home if team_is_home else fair_away
    e = fv - poly_price
    return EdgeResult(edge_pct=e, fair_value=fv) if e > 0 else None

def average_fair_values(lines: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(h for h,_ in lines)/len(lines), sum(a for _,a in lines)/len(lines)