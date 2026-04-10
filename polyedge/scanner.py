from __future__ import annotations
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta
from polyedge.config import Config
from polyedge.models import OddsLine, PolyMarket, Signal
from polyedge.matching.matcher import find_matching_odds
from polyedge.edge.calculator import devig, calculate_edge, average_fair_values
from polyedge.edge.kelly import quarter_kelly_size
from polyedge.db.signals import insert_signal, get_signals, resolve_signal, get_bankroll, get_signal_by_id
from polyedge.execution.polymarket import PolymarketExecutor
from polyedge.execution.pinnacle import PinnacleExecutor
from polyedge.execution.stake import StakeExecutor

def auto_resolve(conn, poly_markets: list) -> list[tuple]:
    """Resolve pending signals where Polymarket price has settled (>0.95 or <0.05)."""
    price_map = {m.market_id: m.price_yes for m in poly_markets}
    # For resolution, we check both 'pending' and 'executed'
    pending = get_signals(conn, status="pending")
    executed = get_signals(conn, status="executed")
    to_check = pending + executed
    
    resolved = []
    for sig in to_check:
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


async def get_total_live_balance(config: Config) -> float:
    """Fetch live balances from all active platforms and sum them up."""
    total = 0.0
    tasks = []
    if config.polymarket_key:
        tasks.append(PolymarketExecutor(config.polymarket_key).get_balance())
    if config.pinnacle_api_key:
        tasks.append(PinnacleExecutor(config.pinnacle_api_key).get_balance())
    if config.stake_api_key:
        tasks.append(StakeExecutor(config.stake_api_key).get_balance())
    
    if not tasks:
        return 0.0
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for res in results:
        if isinstance(res, (float, int)):
            total += res
    return total


async def execute_arbitrage(config: Config, signal: Signal, token_id: str, hedge_source: str, hedge_market_id: str | None):
    """Perform real trades on both platforms."""
    poly_exec = PolymarketExecutor(config.polymarket_key)
    if hedge_source == "stake":
        hedge_exec = StakeExecutor(config.stake_api_key)
    else:
        hedge_exec = PinnacleExecutor(config.pinnacle_api_key)
    
    print(f"[exec] EXECUTION START: {signal.team1} vs {signal.team2}")
    if not hedge_market_id:
        print(f"[exec] Missing market_id or outcome_id for {hedge_source}, skipping execution")
        return
    
    # 1. Start both trades concurrently to minimize latency risk
    poly_task = asyncio.create_task(poly_exec.place_order(
        token_id=token_id, 
        side="BUY", 
        size_usd=signal.suggested_size, 
        price=signal.poly_price
    ))
    
    hedge_task = asyncio.create_task(hedge_exec.place_order(
        market_id=hedge_market_id,
        side="BUY",
        size_usd=signal.hedge_size,
        price=signal.hedge_odds
    ))
    
    results = await asyncio.gather(poly_task, hedge_task, return_exceptions=True)
    for i, res in enumerate(results):
        platform = "Polymarket" if i == 0 else hedge_source.title()
        if isinstance(res, Exception):
            print(f"[exec] {platform} CRITICAL ERROR: {res}")
        elif not res.success:
            print(f"[exec] {platform} FAILED: {res.error}")
        else:
            print(f"[exec] {platform} SUCCESS: Order {res.order_id}")


async def run_scan(poly_markets, odds_lines, config: Config, conn) -> list[Signal]:
    threshold = config.scanner.edge_threshold
    
    # DYNAMIC BANKROLL ALLOCATION
    if config.scanner.execution_enabled:
        bankroll = await get_total_live_balance(config)
        print(f"[scanner] Live Bankroll fetched: ${bankroll:,.2f}")
        if bankroll < 10.0:
            print("[scanner] WARNING: Low balance, skipping execution.")
            # Fallback to DB bankroll for signal generation only (no execution)
            bankroll = get_bankroll(conn)
    else:
        bankroll = get_bankroll(conn)
        
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)

    def _tz(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]
    # Check both pending and executed to avoid duplicates
    active_sigs = get_signals(conn, status="pending") + get_signals(conn, status="executed")
    active_ids = {s.poly_market_id for s in active_sigs}
    
    signals = []

    matches_found = 0
    for market in poly_markets:
        if market.market_id in active_ids: continue
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
        best_line_yes = max(
            match.matched_lines,
            key=lambda l: l.odds_away if match.team_is_home else l.odds_home,
        )
        h_odds_yes = best_line_yes.odds_away if match.team_is_home else best_line_yes.odds_home
        arb_cost_yes = p_yes + (1.0 / h_odds_yes)
        arb_profit_yes = (1.0 / arb_cost_yes) - 1.0 if arb_cost_yes < 1.0 else -1.0
        
        p_no = 1.0 - market.price_yes
        best_line_no = max(
            match.matched_lines,
            key=lambda l: l.odds_home if match.team_is_home else l.odds_away,
        )
        h_odds_no = best_line_no.odds_home if match.team_is_home else best_line_no.odds_away
        arb_cost_no = p_no + (1.0 / h_odds_no)
        arb_profit_no = (1.0 / arb_cost_no) - 1.0 if arb_cost_no < 1.0 else -1.0

        # Choose the best arbitrage opportunity
        if arb_profit_yes > arb_profit_no and arb_profit_yes >= threshold:
            bet_yes = True
            entry_price = p_yes
            hedge_odds = h_odds_yes
            hedge_source = best_line_yes.source
            hedge_market_id = best_line_yes.away_outcome_id if match.team_is_home else best_line_yes.home_outcome_id
            arb_profit = arb_profit_yes
            fair_val = fh if match.team_is_home else fa
        elif arb_profit_no >= threshold:
            bet_yes = False
            entry_price = p_no
            hedge_odds = h_odds_no
            hedge_source = best_line_no.source
            hedge_market_id = best_line_no.home_outcome_id if match.team_is_home else best_line_no.away_outcome_id
            arb_profit = arb_profit_no
            fair_val = fa if match.team_is_home else fh
        else:
            continue

        # Scaling Position Size proportionally to Total Bankroll
        size, frac = quarter_kelly_size(arb_profit, fair_val, bankroll)
        
        # Final safety check
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
        
        # REAL MONEY EXECUTION
        if config.scanner.execution_enabled and bankroll >= 10.0:
            await execute_arbitrage(config, sig, market.token_id_yes, hedge_source, hedge_market_id)
            sig.status = "executed"

        insert_signal(conn, sig)
        signals.append(sig)
    
    if matches_found > 0:
        print(f"[scanner] Finished. Found {matches_found} total matchup matches.")
        
    return signals
