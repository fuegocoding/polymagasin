from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from polyedge.config import Config
from polyedge.models import OddsLine, PolyMarket, Signal
from polyedge.matching.matcher import find_matching_odds
from polyedge.edge.calculator import devig, calculate_edge, average_fair_values
from polyedge.edge.kelly import quarter_kelly_size
from polyedge.db.signals import insert_signal

async def run_scan(poly_markets, odds_lines, config: Config, conn) -> list[Signal]:
    threshold = config.scanner.edge_threshold
    bankroll = config.scanner.bankroll
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)

    def _tz(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]
    signals = []

    for market in poly_markets:
        match = find_matching_odds(market, fresh)
        if not match: continue
        pairs = [devig(l.odds_home, l.odds_away) for l in match.matched_lines]
        fh, fa = average_fair_values(pairs)
        er = calculate_edge(market.price_yes, fh, fa, match.team_is_home)
        if not er or er.edge_pct < threshold: continue
        size, frac = quarter_kelly_size(er.edge_pct, er.fair_value, bankroll)
        sources = ",".join(sorted({l.source for l in match.matched_lines}))
        league = match.matched_lines[0].league
        sig = Signal(
            timestamp=now, sport=market.sport, league=league,
            team1=market.team_yes if match.team_is_home else market.team_no,
            team2=market.team_no if match.team_is_home else market.team_yes,
            game_date=market.game_date, edge_pct=er.edge_pct,
            poly_price=market.price_yes, poly_market_id=market.market_id,
            fair_value=er.fair_value, kelly_fraction=frac, suggested_size=size,
            sources_used=sources,
        )
        insert_signal(conn, sig)
        signals.append(sig)
    return signals