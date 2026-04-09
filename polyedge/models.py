from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass
class OddsLine:
    source: str
    sport: str
    league: str
    team1: str
    team2: str
    game_date: datetime
    odds_home: float
    odds_away: float
    fetched_at: datetime

@dataclass
class PolyMarket:
    market_id: str
    question: str
    token_id_yes: str
    price_yes: float
    sport: str
    team_yes: str
    team_no: str
    game_date: datetime
    url: str

@dataclass
class Signal:
    timestamp: datetime
    sport: str
    league: str
    team1: str
    team2: str
    game_date: datetime
    edge_pct: float
    poly_price: float
    poly_market_id: str
    fair_value: float
    kelly_fraction: float
    suggested_size: float
    sources_used: str
    hedge_odds: float | None = None
    hedge_size: float | None = None
    arb_profit: float | None = None
    hedge_cost_pct: float | None = None
    status: str = "pending"
    outcome_price: float | None = None
    pnl: float | None = None
    id: int | None = None