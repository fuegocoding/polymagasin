from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from polyedge.config import Config
from polyedge.models import OddsLine, PolyMarket, Signal
from polyedge.matching.matcher import find_matching_odds
from polyedge.edge.calculator import devig, calculate_edge, average_fair_values
from polyedge.edge.kelly import quarter_kelly_size
from polyedge.db.signals import insert_signal, get_signals, resolve_signal

def auto_resolve(conn, poly_markets: list) -> list[tuple]:
    """Resolve pending signals where Polymarket price has settled (>0.95 or <0.05)."""
    price_map = {m.market_id: m.price_yes for m in poly_markets}
    pending = get_signals(conn, status="pending")
    resolved = []
    for sig in pending:
        current_yes = price_map.get(sig.poly_market_id)
        if current_yes is None:
            continue
        # Determine if this was a YES or NO bet from sources_used suffix
        bet_yes = not sig.sources_used.endswith(":NO")
        current_entry = current_yes if bet_yes else (1.0 - current_yes)

        if current_yes >= 0.95:
            outcome = "won" if bet_yes else "lost"
            resolve_signal(conn, sig.id, outcome, current_entry)
            resolved.append((sig, outcome, current_entry))
        elif current_yes <= 0.05:
            outcome = "lost" if bet_yes else "won"
            resolve_signal(conn, sig.id, outcome, current_entry)
            resolved.append((sig, outcome, current_entry))
    return resolved


def revalidate_pending(conn, poly_markets: list, odds_lines: list, config: Config) -> list[tuple]:
    """
    For each pending signal, check if the edge is still positive at current prices.
    Cancel signals whose edge has gone negative (price moved against us).
    Returns list of (signal, current_price, current_edge) for all still-valid signals.
    """
    price_map = {m.market_id: m for m in poly_markets}
    pending = get_signals(conn, status="pending")
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)

    def _tz(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]

    cancelled = []
    for sig in pending:
        market = price_map.get(sig.poly_market_id)
        if market is None:
            continue  # market not in current fetch, can't validate
        if not fresh:
            continue  # no fresh odds to validate against
        # Grace period: don't cancel signals younger than one scan interval
        if (now - _tz(sig.timestamp)) < timedelta(minutes=config.scanner.scan_interval_minutes):
            continue

        match = find_matching_odds(market, fresh)
        if not match:
            continue  # no odds match, can't validate

        pairs = [devig(l.odds_home, l.odds_away) for l in match.matched_lines]
        fh, fa = average_fair_values(pairs)
        bet_yes = not sig.sources_used.endswith(":NO")
        if bet_yes:
            er = calculate_edge(market.price_yes, fh, fa, match.team_is_home)
        else:
            er = calculate_edge(1.0 - market.price_yes, fa, fh, match.team_is_home)

        if er is None or er.edge_pct < config.scanner.edge_threshold:
            # Edge gone — cancel the signal
            current_price = market.price_yes if bet_yes else (1.0 - market.price_yes)
            conn.execute("UPDATE signals SET status='cancelled',outcome_price=? WHERE id=?",
                         (current_price, sig.id))
            conn.commit()
            cancelled.append((sig, current_price, er.edge_pct if er else current_price - sig.fair_value))

    return cancelled


async def run_scan(poly_markets, odds_lines, config: Config, conn) -> list[Signal]:
    threshold = config.scanner.edge_threshold
    bankroll = config.scanner.bankroll
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)

    def _tz(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]

    # Skip markets already being tracked as pending (not cancelled/resolved)
    pending = {s.poly_market_id for s in get_signals(conn, status="pending")}

    signals = []

    for market in poly_markets:
        if market.market_id in pending:
            continue
        # Skip markets that have already settled (price near 0 or 1)
        if market.price_yes >= 0.95 or market.price_yes <= 0.05:
            continue
        match = find_matching_odds(market, fresh)
        if not match: continue
        pairs = [devig(l.odds_home, l.odds_away) for l in match.matched_lines]
        fh, fa = average_fair_values(pairs)
        sources = ",".join(sorted({l.source for l in match.matched_lines}))
        league = match.matched_lines[0].league

        # Check YES side: buy YES if price_yes < fair_yes
        er_yes = calculate_edge(market.price_yes, fh, fa, match.team_is_home)
        # Check NO side: buy NO if price_no = (1 - price_yes) < fair_no
        price_no = 1.0 - market.price_yes
        # fair_no is the complement fair value for the opposing team
        er_no = calculate_edge(price_no, fa, fh, match.team_is_home)

        # Pick whichever side has the larger edge (if any)
        candidates = [(er_yes, True), (er_no, False)]
        best_er, bet_yes = max(
            ((er, by) for er, by in candidates if er and er.edge_pct >= threshold),
            key=lambda x: x[0].edge_pct,
            default=(None, True),
        )
        if best_er is None:
            continue

        # For NO bets, the "poly price" is the NO token price
        entry_price = market.price_yes if bet_yes else price_no
        # team_yes bets YES on team_yes winning; NO bet means betting team_no wins
        t1 = market.team_yes if bet_yes == match.team_is_home else market.team_no
        t2 = market.team_no  if bet_yes == match.team_is_home else market.team_yes
        bet_side = "YES" if bet_yes else "NO"

        size, frac = quarter_kelly_size(best_er.edge_pct, best_er.fair_value, bankroll)
        sig = Signal(
            timestamp=now, sport=market.sport, league=league,
            team1=t1, team2=t2,
            game_date=market.game_date, edge_pct=best_er.edge_pct,
            poly_price=entry_price, poly_market_id=market.market_id,
            fair_value=best_er.fair_value, kelly_fraction=frac, suggested_size=size,
            sources_used=f"{sources}:{bet_side}",
        )
        insert_signal(conn, sig)
        signals.append(sig)
    return signals