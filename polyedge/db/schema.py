import sqlite3

_CREATE_SIGNALS = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    sport           TEXT NOT NULL,
    league          TEXT NOT NULL,
    team1           TEXT NOT NULL,
    team2           TEXT NOT NULL,
    game_date       TEXT NOT NULL,
    edge_pct        REAL NOT NULL,
    poly_price      REAL NOT NULL,
    poly_market_id  TEXT NOT NULL,
    fair_value      REAL NOT NULL,
    kelly_fraction  REAL NOT NULL,
    suggested_size  REAL NOT NULL,
    sources_used    TEXT NOT NULL,
    hedge_odds      REAL,
    hedge_size      REAL,
    arb_profit      REAL,
    hedge_cost_pct  REAL,
    status          TEXT NOT NULL DEFAULT 'pending',
    outcome_price   REAL,
    pnl             REAL
)"""

_CREATE_SCAN_LOGS = """
CREATE TABLE IF NOT EXISTS scan_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL,
    markets_scanned  INTEGER NOT NULL,
    signals_found    INTEGER NOT NULL,
    sources_active   TEXT NOT NULL,
    duration_ms      INTEGER NOT NULL
)"""

_CREATE_BANKROLL = """
CREATE TABLE IF NOT EXISTS bankroll (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    balance     REAL NOT NULL,
    updated_at  TEXT NOT NULL
)"""

_CREATE_BANKROLL_HISTORY = """
CREATE TABLE IF NOT EXISTS bankroll_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    balance     REAL NOT NULL,
    change      REAL NOT NULL,
    reason      TEXT
)"""

def init_db(path: str) -> sqlite3.Connection:
    import os
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_SIGNALS)
    conn.execute(_CREATE_SCAN_LOGS)
    conn.execute(_CREATE_BANKROLL)
    conn.execute(_CREATE_BANKROLL_HISTORY)
    # Initialize bankroll if empty
    conn.execute("INSERT OR IGNORE INTO bankroll (id, balance, updated_at) VALUES (1, 1000.0, datetime('now'))")
    conn.commit()
    return conn