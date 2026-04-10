from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from polyedge.models import Signal
from typing import Any

def _is_pg(conn: Any) -> bool:
    return not isinstance(conn, sqlite3.Connection)

def _get_placeholder(conn: Any) -> str:
    return "%s" if _is_pg(conn) else "?"

def _execute(conn: Any, sql: str, params: tuple = ()) -> Any:
    """Helper to execute SQL across different dialects."""
    if _is_pg(conn):
        sql = sql.replace("?", "%s")
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    else:
        return conn.execute(sql, params)

def insert_signal(conn: Any, signal: Signal) -> int:
    placeholder = _get_placeholder(conn)
    sql = f"""INSERT INTO signals
           (timestamp,sport,league,team1,team2,game_date,edge_pct,poly_price,
            poly_market_id,fair_value,kelly_fraction,suggested_size,sources_used,status,
            hedge_odds,hedge_size,arb_profit,hedge_cost_pct,hedge_selection_id)
           VALUES ({','.join([placeholder]*19)})"""
    
    params = (signal.timestamp.isoformat(), signal.sport, signal.league,
         signal.team1, signal.team2, signal.game_date.isoformat(),
         signal.edge_pct, signal.poly_price, signal.poly_market_id,
         signal.fair_value, signal.kelly_fraction, signal.suggested_size,
         signal.sources_used, signal.status, 
         signal.hedge_odds, signal.hedge_size, signal.arb_profit, signal.hedge_cost_pct,
         signal.hedge_selection_id)
    
    if _is_pg(conn):
        sql += " RETURNING id"
        cur = conn.cursor()
        cur.execute(sql, params)
        row_id = cur.fetchone()['id']
        conn.commit()
        return row_id
    else:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid

def get_signal_by_id(conn: Any, sid: int) -> Signal:
    cur = _execute(conn, "SELECT * FROM signals WHERE id=?", (sid,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(f"Signal {sid} not found")
    return _row(row)

def get_bankroll(conn: Any) -> float:
    cur = _execute(conn, "SELECT balance FROM bankroll WHERE id=1")
    row = cur.fetchone()
    return float(row["balance"]) if row else 1000.0

def update_bankroll(conn: Any, change: float, reason: str) -> None:
    _execute(conn, "UPDATE bankroll SET balance = balance + ?, updated_at = ? WHERE id=1", 
             (change, datetime.now().isoformat()))
    new_bal = get_bankroll(conn)
    _execute(conn, "INSERT INTO bankroll_history (timestamp, balance, change, reason) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), new_bal, change, reason),
    )
    conn.commit()

def get_signals(conn: Any, sport=None, min_edge=0.0, status=None) -> list[Signal]:
    placeholder = _get_placeholder(conn)
    q = f"SELECT * FROM signals WHERE edge_pct >= {placeholder}"
    p: list = [min_edge]
    if sport:
        q += f" AND sport={placeholder}"; p.append(sport)
    if status:
        q += f" AND status={placeholder}"; p.append(status)
    q += " ORDER BY timestamp DESC"
    
    cur = _execute(conn, q, tuple(p))
    return [_row(r) for r in cur.fetchall()]

def resolve_signal(conn: Any, sid: int, status: str, outcome_price: float) -> None:
    s = get_signal_by_id(conn, sid)
    if status == "won":
        poly_pnl = s.suggested_size * (1.0 / s.poly_price - 1.0)
        hedge_pnl = -s.hedge_size if s.hedge_size else 0.0
    elif status == "lost":
        poly_pnl = -s.suggested_size
        hedge_pnl = s.hedge_size * (s.hedge_odds - 1.0) if s.hedge_size and s.hedge_odds else 0.0
    else: # push / cancelled
        poly_pnl = 0.0
        hedge_pnl = 0.0
    
    total_pnl = poly_pnl + hedge_pnl
    _execute(conn, "UPDATE signals SET status=?,outcome_price=?,pnl=? WHERE id=?",
                 (status, outcome_price, total_pnl, sid))
    if status in ("won", "lost"):
        update_bankroll(conn, total_pnl, f"Signal {sid} resolved as {status}")
    conn.commit()

def get_pnl_by_sport(conn: Any) -> dict[str, float]:
    cur = _execute(conn, "SELECT sport, SUM(pnl) as total FROM signals WHERE pnl IS NOT NULL GROUP BY sport")
    rows = cur.fetchall()
    return {r["sport"]: float(r["total"]) for r in rows}

def log_scan(conn: Any, markets_scanned, signals_found, sources_active, duration_ms):
    _execute(conn, 
        "INSERT INTO scan_logs (timestamp,markets_scanned,signals_found,sources_active,duration_ms) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), markets_scanned, signals_found,
         ",".join(sources_active), duration_ms),
    )
    conn.commit()

def _row(row: Any) -> Signal:
    # helper to get value if column exists, else None
    def g(key):
        try: return row[key]
        except (IndexError, KeyError, sqlite3.OperationalError, Exception): return None

    return Signal(
        id=row["id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        sport=row["sport"], league=row["league"],
        team1=row["team1"], team2=row["team2"],
        game_date=datetime.fromisoformat(row["game_date"]),
        edge_pct=row["edge_pct"], poly_price=row["poly_price"],
        poly_market_id=row["poly_market_id"], fair_value=row["fair_value"],
        kelly_fraction=row["kelly_fraction"], suggested_size=row["suggested_size"],
        sources_used=row["sources_used"], status=row["status"],
        outcome_price=row["outcome_price"], pnl=row["pnl"],
        hedge_odds=row["hedge_odds"], hedge_size=row["hedge_size"],
        arb_profit=g("arb_profit"), 
        hedge_cost_pct=g("hedge_cost_pct"),
        hedge_selection_id=g("hedge_selection_id")
    )
