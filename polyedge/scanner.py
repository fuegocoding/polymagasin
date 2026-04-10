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
    to_check = get_signals(conn, status="pending") + get_signals(conn, status="executed")
    
    resolved = []
    for sig in to_check:
        current_yes = price_map.get(sig.poly_market_id)
        if current_yes is None: continue
        bet_yes = not sig.sources_used.endswith(":NO")
        current_entry = current_yes if bet_yes else (1.0 - current_yes)

        if current_yes >= 0.95:
            outcome = "won" if bet_yes else "lost"
            resolve_signal(conn, sig.id, outcome, current_entry)
            resolved.append((get_signal_by_id(conn, sig.id), outcome, current_entry))
        elif current_yes <= 0.05:
            outcome = "lost" if bet_yes else "won"
            resolve_signal(conn, sig.id, outcome, current_entry)
            resolved.append((get_signal_by_id(conn, sig.id), outcome, current_entry))
    return resolved


async def get_total_live_balance(config: Config) -> dict[str, float]:
    """Fetch live balances from all active platforms and return as a dict."""
    balances = {"total": 0.0, "polymarket": 0.0, "pinnacle": 0.0, "stake": 0.0}
    tasks = []
    names = []
    
    if config.polymarket_key:
        tasks.append(PolymarketExecutor(config.polymarket_key).get_balance())
        names.append("polymarket")
    if config.pinnacle_api_key:
        tasks.append(PinnacleExecutor(config.pinnacle_api_key).get_balance())
        names.append("pinnacle")
    if config.stake_api_key:
        tasks.append(StakeExecutor(config.stake_api_key).get_balance())
        names.append("stake")
    
    if not tasks:
        return balances
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for name, res in zip(names, results):
        if isinstance(res, (float, int)):
            balances[name] = float(res)
            balances["total"] += float(res)
        else:
            print(f"[scanner] Error fetching balance for {name}: {res}")
            
    return balances


async def execute_arbitrage(config: Config, signal: Signal, poly_token_id: str):
    """Perform real trades on both platforms."""
    hedge_platform = signal.sources_used.split(":")[0].lower()
    poly_exec = PolymarketExecutor(config.polymarket_key)
    
    if hedge_platform == "pinnacle":
        hedge_exec = PinnacleExecutor(config.pinnacle_api_key)
    elif hedge_platform == "stake":
        hedge_exec = StakeExecutor(config.stake_api_key)
    else:
        print(f"[exec] ERROR: Unsupported hedge platform {hedge_platform}")
        return

    print(f"[exec] EXECUTION START: {signal.team1} vs {signal.team2} on {hedge_platform}")
    
    # 1. Start both trades concurrently
    poly_task = asyncio.create_task(poly_exec.place_order(
        token_id=poly_token_id, side="BUY", 
        size_usd=signal.suggested_size, price=signal.poly_price
    ))
    
    hedge_task = asyncio.create_task(hedge_exec.place_order(
        selection_id=signal.hedge_selection_id, side="BUY",
        size_usd=signal.hedge_size, price=signal.hedge_odds
    ))
    
    results = await asyncio.gather(poly_task, hedge_task, return_exceptions=True)
    for i, res in enumerate(results):
        platform = "Polymarket" if i == 0 else hedge_platform.capitalize()
        if isinstance(res, Exception): print(f"[exec] {platform} CRITICAL ERROR: {res}")
        elif not res.success: print(f"[exec] {platform} FAILED: {res.error}")
        else: print(f"[exec] {platform} SUCCESS: Order {res.order_id}")


async def run_scan(poly_markets, odds_lines, config: Config, conn) -> list[Signal]:
    threshold = config.scanner.edge_threshold
    
    # DYNAMIC BANKROLL ALLOCATION
    if config.scanner.execution_enabled:
        bal_data = await get_total_live_balance(config)
        bankroll = bal_data["total"]
        print(f"[scanner] Live Bankroll fetched: ${bankroll:,.2f} ({bal_data})")
        if bankroll < 10.0:
            print("[scanner] WARNING: Low balance, skipping execution.")
            bankroll = get_bankroll(conn)
    else:
        bankroll = get_bankroll(conn)
        
    stale = timedelta(minutes=config.scanner.stale_odds_minutes)
    now = datetime.now(timezone.utc)
    def _tz(dt): return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    fresh = [l for l in odds_lines if (now - _tz(l.fetched_at)) <= stale]
    active_ids = {s.poly_market_id for s in (get_signals(conn, status="pending") + get_signals(conn, status="executed"))}
    
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
        
        # Arb Eval
        p_yes, p_no = market.price_yes, 1.0 - market.price_yes
        # Hedge logic
        best_line = match.matched_lines[0]
        h_odds_yes = best_line.odds_away if match.team_is_home else best_line.odds_home
        h_sid_yes = best_line.selection_id_away if match.team_is_home else best_line.selection_id_home
        
        h_odds_no = best_line.odds_home if match.team_is_home else best_line.odds_away
        h_sid_no = best_line.selection_id_home if match.team_is_home else best_line.selection_id_away

        arb_profit_yes = (1.0 / (p_yes + 1.0/h_odds_yes)) - 1.0
        arb_profit_no = (1.0 / (p_no + 1.0/h_odds_no)) - 1.0

        if arb_profit_yes > arb_profit_no and arb_profit_yes >= threshold:
            bet_yes, entry_price, hedge_odds, arb_profit, fair_val = True, p_yes, h_odds_yes, arb_profit_yes, (fh if match.team_is_home else fa)
            poly_token_id, hedge_selection_id = market.token_id_yes, h_sid_yes
        elif arb_profit_no >= threshold:
            bet_yes, entry_price, hedge_odds, arb_profit, fair_val = False, p_no, h_odds_no, arb_profit_no, (fa if match.team_is_home else fh)
            poly_token_id, hedge_selection_id = market.token_id_no, h_sid_no
        else: 
            # Log close calls
            best_profit = max(arb_profit_yes, arb_profit_no)
            if best_profit >= (threshold - 0.02):
                side = "YES" if arb_profit_yes > arb_profit_no else "NO"
                print(f"[debug] {market.question} match found! Profit: {best_profit*100:.2f}% ({side})")
            continue

        size, frac = quarter_kelly_size(arb_profit, fair_val, bankroll)
        if entry_price < 0.01 or not poly_token_id: continue

        sig = Signal(
            timestamp=now, sport=market.sport, league=best_line.league,
            team1=(market.team_yes if bet_yes == match.team_is_home else market.team_no),
            team2=(market.team_no if bet_yes == match.team_is_home else market.team_yes),
            game_date=market.game_date, edge_pct=round(arb_profit, 4),
            poly_price=entry_price, poly_market_id=market.market_id,
            fair_value=round(fair_val, 4), kelly_fraction=frac, suggested_size=size,
            sources_used=f"{best_line.source}:{'YES' if bet_yes else 'NO'}",
            hedge_odds=round(hedge_odds, 4), hedge_size=round((size/entry_price)/hedge_odds, 2),
            arb_profit=round(arb_profit, 4), hedge_cost_pct=round(1.0/hedge_odds, 4),
            hedge_selection_id=hedge_selection_id
        )
        
        if config.scanner.execution_enabled and bankroll >= 10.0:
            await execute_arbitrage(config, sig, poly_token_id)
            sig.status = "executed"

        insert_signal(conn, sig)
        signals.append(sig)
    
    if matches_found > 0:
        print(f"[scanner] Finished. Found {matches_found} total matchup matches.")
        
    return signals
