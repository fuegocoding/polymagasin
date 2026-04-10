import sqlite3
import os
from typing import Any

# Dialect-neutral schema definitions
_TABLES = {
    "signals": """
        CREATE TABLE IF NOT EXISTS signals (
            id              SERIAL PRIMARY KEY,
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
        )""",
    "scan_logs": """
        CREATE TABLE IF NOT EXISTS scan_logs (
            id               SERIAL PRIMARY KEY,
            timestamp        TEXT NOT NULL,
            markets_scanned  INTEGER NOT NULL,
            signals_found    INTEGER NOT NULL,
            sources_active   TEXT NOT NULL,
            duration_ms      INTEGER NOT NULL
        )""",
    "bankroll": """
        CREATE TABLE IF NOT EXISTS bankroll (
            id          INTEGER PRIMARY KEY CHECK (id = 1),
            balance     REAL NOT NULL,
            updated_at  TEXT NOT NULL
        )""",
    "bankroll_history": """
        CREATE TABLE IF NOT EXISTS bankroll_history (
            id          SERIAL PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            balance     REAL NOT NULL,
            change      REAL NOT NULL,
            reason      TEXT
        )"""
}

def init_db(config) -> Any:
    """
    Initializes the database (SQLite or PostgreSQL) based on config.
    Returns a connection object.
    """
    if config.database_url:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(config.database_url, cursor_factory=RealDictCursor)
        # PostgreSQL specific adjustments to schema
        # SQLite uses AUTOINCREMENT, Postgres uses SERIAL (handled above)
        # SQLite INTEGER PRIMARY KEY AUTOINCREMENT -> Postgres SERIAL PRIMARY KEY
        # We also need to fix the 'signals' and 'bankroll' id 1 check for Postgres
        with conn.cursor() as cur:
            for sql in _TABLES.values():
                cur.execute(sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY"))
            
            # Initialize bankroll if empty
            cur.execute("SELECT 1 FROM bankroll WHERE id=1")
            if not cur.fetchone():
                from datetime import datetime
                cur.execute("INSERT INTO bankroll (id, balance, updated_at) VALUES (1, 1000.0, %s)", (datetime.now().isoformat(),))
        conn.commit()
        return conn
    else:
        # SQLite
        os.makedirs(os.path.dirname(os.path.abspath(config.db_path)), exist_ok=True)
        conn = sqlite3.connect(config.db_path)
        conn.row_factory = sqlite3.Row
        for sql in _TABLES.values():
            # Postgres SERIAL -> SQLite INTEGER PRIMARY KEY AUTOINCREMENT
            conn.execute(sql.replace("SERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"))
        
        # Initialize bankroll if empty
        conn.execute("INSERT OR IGNORE INTO bankroll (id, balance, updated_at) VALUES (1, 1000.0, datetime('now'))")
        conn.commit()
        return conn
