from __future__ import annotations
import sqlite3
from datetime import datetime, timezone, timedelta
from polyedge.config import Config
from polyedge.models import OddsLine, PolyMarket, Signal
from polyedge.matching.matcher import find_matching_odds
from polyedge.edge.calculator import devig, calculate_edge, average_fair_values
from polyedge.edge.kelly import quarter_kelly_size
from polyedge.db.signals import insert_signal, get_signals, resolve_signal, get_bankroll, get_signal_by_id

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
            updated_sig = get_signal_by_id(conn, sig.id)
            resolved.append((updated_sig, outcome, current_entry))
        elif current_yes <= 0.05:
            outcome = "lost" if bet_yes else "won"
            resolve_signal(conn, sig.id, outcome, current_entry)
            updated_sig = get_signal_by_id(conn, sig.id)
            resolved.append((updated_sig, outcome, current_entry))
    return resolved


async def run_scan(poly_markets, odds_lines, config: Config, conn) -> list[Signal]:
    threshold = config.scanner.edge_threshold
    bankroll = get_bankroll(conn)
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)

    def _tz(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]
    pending = {s.poly_market_id for s in get_signals(conn, status="pending")}
    signals = []

    matches_found = 0
    for market in poly_markets:
        if market.market_id in pending: continue
        if market.price_yes >= 0.95 or market.price_yes <= 0.05: continue
        
        match = find_matching_odds(market, fresh)
        if not match: continue
        
        matches_found += 1
            
        pairs = [devig(l.odds_home, l.odds_away) for l in match.matched_lines]
        fh, fa = average_fair_values(pairs)
        sources = ",".join(sorted({l.source for l in match.matched_lines}))
        league = match.matched_lines[0].league

        # Evaluate both sides for arbitrage potential
        p_yes = market.price_yes
        h_odds_yes = max(l.odds_away if match.team_is_home else l.odds_home for l in match.matched_lines)
        arb_cost_yes = p_yes + (1.0 / h_odds_yes)
        arb_profit_yes = (1.0 / arb_cost_yes) - 1.0 if arb_cost_yes < 1.0 else (1.0 / arb_cost_yes) - 1.0
        
        p_no = 1.0 - market.price_yes
        h_odds_no = max(l.odds_home if match.team_is_home else l.odds_away for l in match.matched_lines)
        arb_cost_no = p_no + (1.0 / h_odds_no)
        arb_profit_no = (1.0 / arb_cost_no) - 1.0 if arb_cost_no < 1.0 else (1.0 / arb_cost_no) - 1.0

        # Log close calls (within 2% of threshold)
        best_profit = max(arb_profit_yes, arb_profit_no)
        if best_profit >= (threshold - 0.02):
            side = "YES" if arb_profit_yes > arb_profit_no else "NO"
            print(f"[debug] {market.question} match found! Profit: {best_profit*100:.2f}% ({side})")

        # Choose the best arbitrage opportunity
        if arb_profit_yes > arb_profit_no and arb_profit_yes >= threshold:
            bet_yes = True
            entry_price = p_yes
            hedge_odds = h_odds_yes
            arb_profit = arb_profit_yes
            fair_val = fh if match.team_is_home else fa
        elif arb_profit_no >= threshold:
            bet_yes = False
            entry_price = p_no
            hedge_odds = h_odds_no
            arb_profit = arb_profit_no
            fair_val = fa if match.team_is_home else fh
        else:
            continue

        # Use arb_profit as the 'edge' for Kelly to keep it consistent
        size, frac = quarter_kelly_size(arb_profit, fair_val, bankroll)
        
        # Final safety check: if entry_price is too low or high, kelly might get wild
        if entry_price < 0.01: continue

        hedge_size = (size / entry_price) / hedge_odds
        
        t1 = market.team_yes if bet_yes == match.team_is_home else market.team_no
        t2 = market.team_no  if bet_yes == match.team_is_home else market.team_yes
        bet_side = "YES" if bet_yes else "NO"

        sig = Signal(
            timestamp=now, sport=market.sport, league=league,
            team1=t1, team2=t2,
            game_date=market.game_date, edge_pct=round(arb_profit, 4),
            poly_price=entry_price, poly_market_id=market.market_id,
            fair_value=round(fair_val, 4), kelly_fraction=frac, suggested_size=size,
            sources_used=f"{sources}:{bet_side}",
            hedge_odds=round(hedge_odds, 4), hedge_size=round(hedge_size, 2),
            arb_profit=round(arb_profit, 4), hedge_cost_pct=round(1.0/hedge_odds, 4)
        )
        insert_signal(conn, sig)
        signals.append(sig)
    
    if matches_found > 0:
        print(f"[scanner] Finished. Found {matches_found} total matchup matches.")
        
    return signals
