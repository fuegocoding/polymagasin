# PolyEdge — Full Implementation Handoff

## Your job
Implement the PolyEdge arbitrage scanner from scratch, following the plan below exactly. Work task by task, in order. For each task: write the failing test first, run it to confirm it fails, implement the code, run it to confirm it passes, then commit. Do not skip steps. Do not add features beyond what's specified.

## Project context
- **What:** A Python CLI tool that scans Polymarket sports prediction markets against sportsbook odds (Pinnacle, Stake, Mise-o-jeu) to detect ≥5% edge opportunities. All signals are logged to SQLite for paper trading.
- **Working directory:** `c:/Users/charl/Documents/Code/polymagasin/` (clean git repo, no files yet)
- **Platform:** Windows 11, bash shell (use Unix paths)
- **Python:** 3.11+

## Tech stack
- httpx (async HTTP)
- typer (CLI)
- rich (table output)
- rapidfuzz (fuzzy matching)
- tomllib (stdlib, config)
- sqlite3 (stdlib, DB)
- pytest + pytest-asyncio + respx (testing)

---

## File map (create all of these)

```
polyedge/
  __init__.py
  config.py
  models.py
  scanner.py
  fetchers/
    __init__.py
    base.py
    polymarket.py
    pinnacle.py
    stake.py
    miseonjeu.py
  matching/
    __init__.py
    normalizer.py
    matcher.py
    aliases.json
  edge/
    __init__.py
    calculator.py
    kelly.py
  db/
    __init__.py
    schema.py
    signals.py
  cli/
    __init__.py
    display.py
    main.py
tests/
  conftest.py
  test_config.py
  test_models.py
  db/test_signals.py
  fetchers/test_polymarket.py
  fetchers/test_pinnacle.py
  fetchers/test_stake.py
  matching/test_normalizer.py
  matching/test_matcher.py
  edge/test_calculator.py
  edge/test_kelly.py
  test_scanner.py
config.toml
requirements.txt
pytest.ini
main.py
```

---

## Task 1 — Project scaffolding

### `requirements.txt`
```
httpx>=0.27.0
typer>=0.12.0
rich>=13.7.0
rapidfuzz>=3.6.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
respx>=0.21.0
```

### `pytest.ini`
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

### `config.toml`
```toml
[scanner]
edge_threshold = 0.05
scan_interval_minutes = 30
stale_odds_minutes = 30
bankroll = 500.0

[sports]
enabled = ["nba", "nhl", "mlb", "epl"]

[sources]
pinnacle = true
stake = true
miseonjeu = true

[db]
path = "polyedge.db"

[keys]
# stake_api_key = ""
```

### Create all `__init__.py` files and test subdirs:
```bash
mkdir -p polyedge/fetchers polyedge/matching polyedge/edge polyedge/db polyedge/cli
touch polyedge/__init__.py polyedge/fetchers/__init__.py polyedge/matching/__init__.py
touch polyedge/edge/__init__.py polyedge/db/__init__.py polyedge/cli/__init__.py
mkdir -p tests/db tests/fetchers tests/matching tests/edge
touch tests/__init__.py tests/db/__init__.py tests/fetchers/__init__.py
touch tests/matching/__init__.py tests/edge/__init__.py
```

### `tests/conftest.py`
```python
import pytest
from polyedge.db.schema import init_db

@pytest.fixture
def db():
    conn = init_db(":memory:")
    yield conn
    conn.close()
```

### `main.py`
```python
from polyedge.cli.main import app

if __name__ == "__main__":
    app()
```

```bash
pip install -r requirements.txt
git add .
git commit -m "chore: project scaffolding"
```

---

## Task 2 — Core models

### `tests/test_models.py`
```python
from datetime import datetime, timezone
from polyedge.models import OddsLine, PolyMarket, Signal

def _now():
    return datetime.now(timezone.utc)

def test_odds_line_fields():
    line = OddsLine(
        source="pinnacle", sport="nba", league="NBA",
        team1="Lakers", team2="Warriors",
        game_date=_now(), odds_home=1.85, odds_away=2.10, fetched_at=_now(),
    )
    assert line.source == "pinnacle"
    assert line.odds_home == 1.85

def test_poly_market_fields():
    m = PolyMarket(
        market_id="0xabc", question="Will Lakers beat Warriors?",
        token_id_yes="111", price_yes=0.65, sport="nba",
        team_yes="Lakers", team_no="Warriors",
        game_date=_now(), url="https://polymarket.com/test",
    )
    assert m.price_yes == 0.65

def test_signal_default_status():
    s = Signal(
        timestamp=_now(), sport="nba", league="NBA",
        team1="Lakers", team2="Warriors",
        game_date=_now(), edge_pct=0.10, poly_price=0.65,
        poly_market_id="0xabc", fair_value=0.55,
        kelly_fraction=0.222, suggested_size=27.78,
        sources_used="pinnacle,stake",
    )
    assert s.status == "pending"
    assert s.pnl is None
    assert s.id is None
```

Run: `pytest tests/test_models.py -v` → confirm ImportError

### `polyedge/models.py`
```python
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
    status: str = "pending"
    outcome_price: float | None = None
    pnl: float | None = None
    id: int | None = None
```

Run: `pytest tests/test_models.py -v` → 3 PASSED

```bash
git add polyedge/models.py tests/test_models.py
git commit -m "feat: core data models"
```

---

## Task 3 — Config loader

### `tests/test_config.py`
```python
import tempfile, os
from polyedge.config import load_config

SAMPLE = """\
[scanner]
edge_threshold = 0.07
bankroll = 1000.0
scan_interval_minutes = 15
stale_odds_minutes = 30

[sports]
enabled = ["nba", "nhl"]

[sources]
pinnacle = true
stake = false
miseonjeu = true

[db]
path = "test.db"
"""

def test_load_config_values():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write(SAMPLE); path = f.name
    try:
        cfg = load_config(path)
        assert cfg.scanner.edge_threshold == 0.07
        assert cfg.scanner.bankroll == 1000.0
        assert cfg.sports == ["nba", "nhl"]
        assert cfg.sources["pinnacle"] is True
        assert cfg.sources["stake"] is False
        assert cfg.db_path == "test.db"
    finally:
        os.unlink(path)

def test_load_config_defaults():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        f.write("[scanner]\n"); path = f.name
    try:
        cfg = load_config(path)
        assert cfg.scanner.edge_threshold == 0.05
        assert cfg.scanner.bankroll == 500.0
        assert "nba" in cfg.sports
    finally:
        os.unlink(path)
```

Run: `pytest tests/test_config.py -v` → confirm ImportError

### `polyedge/config.py`
```python
from __future__ import annotations
import tomllib
from dataclasses import dataclass

@dataclass
class ScannerConfig:
    edge_threshold: float = 0.05
    scan_interval_minutes: int = 30
    stale_odds_minutes: int = 30
    bankroll: float = 500.0

@dataclass
class Config:
    scanner: ScannerConfig
    sports: list[str]
    sources: dict[str, bool]
    db_path: str
    stake_api_key: str = ""

def load_config(path: str = "config.toml") -> Config:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    raw = data.get("scanner", {})
    scanner = ScannerConfig(
        edge_threshold=raw.get("edge_threshold", 0.05),
        scan_interval_minutes=raw.get("scan_interval_minutes", 30),
        stale_odds_minutes=raw.get("stale_odds_minutes", 30),
        bankroll=raw.get("bankroll", 500.0),
    )
    return Config(
        scanner=scanner,
        sports=data.get("sports", {}).get("enabled", ["nba", "nhl", "mlb", "epl"]),
        sources=data.get("sources", {"pinnacle": True, "stake": True, "miseonjeu": True}),
        db_path=data.get("db", {}).get("path", "polyedge.db"),
        stake_api_key=data.get("keys", {}).get("stake_api_key", ""),
    )
```

Run: `pytest tests/test_config.py -v` → 2 PASSED

```bash
git add polyedge/config.py tests/test_config.py
git commit -m "feat: TOML config loader"
```

---

## Task 4 — Database schema + signals CRUD

### `tests/db/test_signals.py`
```python
from datetime import datetime, timezone
import pytest
from polyedge.models import Signal
from polyedge.db.signals import insert_signal, get_signals, get_signal_by_id, resolve_signal, get_pnl_by_sport

def _signal(**kw):
    d = dict(
        timestamp=datetime.now(timezone.utc), sport="nba", league="NBA",
        team1="Lakers", team2="Warriors",
        game_date=datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc),
        edge_pct=0.10, poly_price=0.65, poly_market_id="0xabc",
        fair_value=0.55, kelly_fraction=0.222, suggested_size=27.78,
        sources_used="pinnacle,stake",
    )
    d.update(kw)
    return Signal(**d)

def test_insert_and_retrieve(db):
    sid = insert_signal(db, _signal())
    assert sid == 1
    r = get_signal_by_id(db, sid)
    assert r.sport == "nba"
    assert r.edge_pct == pytest.approx(0.10)
    assert r.status == "pending"

def test_filter_by_sport(db):
    insert_signal(db, _signal(sport="nba"))
    insert_signal(db, _signal(sport="nhl", team1="Canadiens", team2="Leafs"))
    assert len(get_signals(db, sport="nba")) == 1

def test_filter_by_min_edge(db):
    insert_signal(db, _signal(edge_pct=0.03))
    insert_signal(db, _signal(edge_pct=0.08))
    r = get_signals(db, min_edge=0.05)
    assert len(r) == 1
    assert r[0].edge_pct == pytest.approx(0.08)

def test_resolve_won(db):
    sid = insert_signal(db, _signal(poly_price=0.65, suggested_size=27.78))
    resolve_signal(db, sid, "won", 1.0)
    s = get_signal_by_id(db, sid)
    assert s.status == "won"
    assert s.pnl == pytest.approx(27.78 * (1.0 / 0.65 - 1.0), rel=1e-4)

def test_resolve_lost(db):
    sid = insert_signal(db, _signal(suggested_size=27.78))
    resolve_signal(db, sid, "lost", 0.0)
    assert get_signal_by_id(db, sid).pnl == pytest.approx(-27.78)

def test_resolve_push(db):
    sid = insert_signal(db, _signal())
    resolve_signal(db, sid, "push", 0.5)
    assert get_signal_by_id(db, sid).pnl == pytest.approx(0.0)

def test_pnl_by_sport(db):
    id1 = insert_signal(db, _signal(sport="nba", suggested_size=100.0, poly_price=0.5))
    id2 = insert_signal(db, _signal(sport="nhl", team1="A", team2="B", suggested_size=50.0))
    resolve_signal(db, id1, "won", 1.0)
    resolve_signal(db, id2, "lost", 0.0)
    pnl = get_pnl_by_sport(db)
    assert pnl["nba"] == pytest.approx(100.0)
    assert pnl["nhl"] == pytest.approx(-50.0)
```

Run: `pytest tests/db/test_signals.py -v` → confirm ImportError

### `polyedge/db/schema.py`
```python
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

def init_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_SIGNALS)
    conn.execute(_CREATE_SCAN_LOGS)
    conn.commit()
    return conn
```

### `polyedge/db/signals.py`
```python
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from polyedge.models import Signal

def insert_signal(conn: sqlite3.Connection, signal: Signal) -> int:
    cur = conn.execute(
        """INSERT INTO signals
           (timestamp,sport,league,team1,team2,game_date,edge_pct,poly_price,
            poly_market_id,fair_value,kelly_fraction,suggested_size,sources_used,status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (signal.timestamp.isoformat(), signal.sport, signal.league,
         signal.team1, signal.team2, signal.game_date.isoformat(),
         signal.edge_pct, signal.poly_price, signal.poly_market_id,
         signal.fair_value, signal.kelly_fraction, signal.suggested_size,
         signal.sources_used, signal.status),
    )
    conn.commit()
    return cur.lastrowid

def get_signal_by_id(conn: sqlite3.Connection, sid: int) -> Signal:
    row = conn.execute("SELECT * FROM signals WHERE id=?", (sid,)).fetchone()
    if row is None:
        raise ValueError(f"Signal {sid} not found")
    return _row(row)

def get_signals(conn, sport=None, min_edge=0.0, status=None) -> list[Signal]:
    q = "SELECT * FROM signals WHERE edge_pct >= ?"
    p: list = [min_edge]
    if sport:
        q += " AND sport=?"; p.append(sport)
    if status:
        q += " AND status=?"; p.append(status)
    q += " ORDER BY timestamp DESC"
    return [_row(r) for r in conn.execute(q, p).fetchall()]

def resolve_signal(conn, sid: int, status: str, outcome_price: float) -> None:
    s = get_signal_by_id(conn, sid)
    pnl = (s.suggested_size * (1.0 / s.poly_price - 1.0) if status == "won"
           else -s.suggested_size if status == "lost" else 0.0)
    conn.execute("UPDATE signals SET status=?,outcome_price=?,pnl=? WHERE id=?",
                 (status, outcome_price, pnl, sid))
    conn.commit()

def get_pnl_by_sport(conn) -> dict[str, float]:
    rows = conn.execute(
        "SELECT sport, SUM(pnl) as total FROM signals WHERE pnl IS NOT NULL GROUP BY sport"
    ).fetchall()
    return {r["sport"]: r["total"] for r in rows}

def log_scan(conn, markets_scanned, signals_found, sources_active, duration_ms):
    conn.execute(
        "INSERT INTO scan_logs (timestamp,markets_scanned,signals_found,sources_active,duration_ms) VALUES (?,?,?,?,?)",
        (datetime.now(timezone.utc).isoformat(), markets_scanned, signals_found,
         ",".join(sources_active), duration_ms),
    )
    conn.commit()

def _row(row: sqlite3.Row) -> Signal:
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
    )
```

Run: `pytest tests/db/test_signals.py -v` → 7 PASSED

```bash
git add polyedge/db/ tests/db/
git commit -m "feat: SQLite schema and signal CRUD"
```

---

## Task 5 — Edge calculator

### `tests/edge/test_calculator.py`
```python
import pytest
from polyedge.edge.calculator import devig, implied_prob, calculate_edge, average_fair_values, EdgeResult

def test_implied_prob():
    assert implied_prob(2.00) == pytest.approx(0.50)
    assert implied_prob(1.25) == pytest.approx(0.80)

def test_devig_sums_to_one():
    fh, fa = devig(2.10, 1.80)
    assert fh + fa == pytest.approx(1.0, abs=1e-9)
    assert fh < fa  # 2.10 is the underdog

def test_devig_even_odds():
    fh, fa = devig(2.00, 2.00)
    assert fh == pytest.approx(0.50)
    assert fa == pytest.approx(0.50)

def test_edge_positive():
    r = calculate_edge(poly_price=0.65, fair_home=0.55, fair_away=0.45, team_is_home=True)
    assert r.edge_pct == pytest.approx(0.10)
    assert r.fair_value == pytest.approx(0.55)

def test_edge_negative_returns_none():
    r = calculate_edge(poly_price=0.45, fair_home=0.55, fair_away=0.45, team_is_home=True)
    assert r is None

def test_average_fair_values():
    avg_h, avg_a = average_fair_values([(0.55, 0.45), (0.60, 0.40), (0.50, 0.50)])
    assert avg_h == pytest.approx(0.55)
    assert avg_a == pytest.approx(0.45)
```

Run: `pytest tests/edge/test_calculator.py -v` → confirm ImportError

### `polyedge/edge/calculator.py`
```python
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
    e = poly_price - fv
    return EdgeResult(edge_pct=e, fair_value=fv) if e > 0 else None

def average_fair_values(lines: list[tuple[float, float]]) -> tuple[float, float]:
    return sum(h for h,_ in lines)/len(lines), sum(a for _,a in lines)/len(lines)
```

Run: `pytest tests/edge/test_calculator.py -v` → 6 PASSED

```bash
git add polyedge/edge/calculator.py tests/edge/test_calculator.py
git commit -m "feat: edge calculator — devig and edge %"
```

---

## Task 6 — Kelly criterion

### `tests/edge/test_kelly.py`
```python
import pytest
from polyedge.edge.kelly import quarter_kelly_size

def test_basic():
    size, frac = quarter_kelly_size(0.10, 0.55, 500.0)
    assert frac == pytest.approx(0.10 / 0.45 / 4, rel=1e-4)
    assert size == pytest.approx(frac * 500.0, rel=1e-4)

def test_caps_at_bankroll():
    size, _ = quarter_kelly_size(0.90, 0.05, 500.0)
    assert size <= 500.0

def test_minimum_one_dollar():
    size, _ = quarter_kelly_size(0.051, 0.50, 500.0)
    assert size >= 1.0

def test_zero_edge_raises():
    with pytest.raises(ValueError):
        quarter_kelly_size(0.0, 0.50, 500.0)
```

Run: `pytest tests/edge/test_kelly.py -v` → confirm ImportError

### `polyedge/edge/kelly.py`
```python
def quarter_kelly_size(edge_pct: float, fair_value: float, bankroll: float) -> tuple[float, float]:
    if edge_pct <= 0:
        raise ValueError("edge_pct must be positive")
    full_kelly = edge_pct / (1.0 - fair_value)
    quarter = full_kelly / 4.0
    size = max(min(quarter * bankroll, bankroll), 1.0)
    return round(size, 2), round(quarter, 6)
```

Run: `pytest tests/edge/test_kelly.py -v` → 4 PASSED

```bash
git add polyedge/edge/kelly.py tests/edge/test_kelly.py
git commit -m "feat: quarter-Kelly sizing"
```

---

## Task 7 — Team normalizer + aliases

### `tests/matching/test_normalizer.py`
```python
from polyedge.matching.normalizer import normalize_team

def test_canonical_passthrough():
    assert normalize_team("Lakers", "nba") == "Lakers"

def test_nba_aliases():
    assert normalize_team("Los Angeles Lakers", "nba") == "Lakers"
    assert normalize_team("LA Lakers", "nba") == "Lakers"
    assert normalize_team("Golden State Warriors", "nba") == "Warriors"
    assert normalize_team("GSW", "nba") == "Warriors"

def test_nhl_aliases():
    assert normalize_team("Montreal Canadiens", "nhl") == "Canadiens"
    assert normalize_team("MTL", "nhl") == "Canadiens"

def test_epl_aliases():
    assert normalize_team("Manchester City FC", "epl") == "Man City"

def test_unknown_passthrough():
    assert normalize_team("Unknown FC", "epl") == "Unknown FC"

def test_case_insensitive():
    assert normalize_team("los angeles lakers", "nba") == "Lakers"
```

Run: `pytest tests/matching/test_normalizer.py -v` → confirm ImportError

### `polyedge/matching/aliases.json`

Create this file with the following content (comprehensive alias map for all 4 leagues):

```json
{
  "nba": {
    "Los Angeles Lakers": "Lakers", "LA Lakers": "Lakers", "LAL": "Lakers",
    "Golden State Warriors": "Warriors", "GS Warriors": "Warriors", "GSW": "Warriors",
    "Boston Celtics": "Celtics", "BOS": "Celtics",
    "Miami Heat": "Heat", "MIA": "Heat",
    "Milwaukee Bucks": "Bucks", "MIL": "Bucks",
    "Denver Nuggets": "Nuggets", "DEN": "Nuggets",
    "Phoenix Suns": "Suns", "PHX": "Suns",
    "Memphis Grizzlies": "Grizzlies", "MEM": "Grizzlies",
    "Oklahoma City Thunder": "Thunder", "OKC": "Thunder",
    "Minnesota Timberwolves": "Timberwolves", "MIN": "Timberwolves",
    "New York Knicks": "Knicks", "NYK": "Knicks",
    "Cleveland Cavaliers": "Cavaliers", "CLE": "Cavaliers",
    "Indiana Pacers": "Pacers", "IND": "Pacers",
    "Orlando Magic": "Magic", "ORL": "Magic",
    "Chicago Bulls": "Bulls", "CHI": "Bulls",
    "Atlanta Hawks": "Hawks", "ATL": "Hawks",
    "Philadelphia 76ers": "76ers", "PHI": "76ers",
    "Brooklyn Nets": "Nets", "BKN": "Nets",
    "Toronto Raptors": "Raptors", "TOR": "Raptors",
    "Sacramento Kings": "Kings", "SAC": "Kings",
    "Los Angeles Clippers": "Clippers", "LAC": "Clippers",
    "Portland Trail Blazers": "Blazers", "POR": "Blazers",
    "Utah Jazz": "Jazz", "UTA": "Jazz",
    "New Orleans Pelicans": "Pelicans", "NOP": "Pelicans",
    "San Antonio Spurs": "Spurs", "SAS": "Spurs",
    "Houston Rockets": "Rockets", "HOU": "Rockets",
    "Dallas Mavericks": "Mavericks", "DAL": "Mavericks",
    "Washington Wizards": "Wizards", "WAS": "Wizards",
    "Charlotte Hornets": "Hornets", "CHA": "Hornets",
    "Detroit Pistons": "Pistons", "DET": "Pistons"
  },
  "nhl": {
    "Montreal Canadiens": "Canadiens", "MTL": "Canadiens",
    "Toronto Maple Leafs": "Leafs", "TOR": "Leafs",
    "Boston Bruins": "Bruins", "BOS": "Bruins",
    "Tampa Bay Lightning": "Lightning", "TBL": "Lightning",
    "Florida Panthers": "Panthers", "FLA": "Panthers",
    "Carolina Hurricanes": "Hurricanes", "CAR": "Hurricanes",
    "New York Rangers": "Rangers", "NYR": "Rangers",
    "New York Islanders": "Islanders", "NYI": "Islanders",
    "New Jersey Devils": "Devils", "NJD": "Devils",
    "Philadelphia Flyers": "Flyers", "PHI": "Flyers",
    "Pittsburgh Penguins": "Penguins", "PIT": "Penguins",
    "Washington Capitals": "Capitals", "WSH": "Capitals",
    "Columbus Blue Jackets": "Blue Jackets", "CBJ": "Blue Jackets",
    "Detroit Red Wings": "Red Wings", "DET": "Red Wings",
    "Chicago Blackhawks": "Blackhawks", "CHI": "Blackhawks",
    "Nashville Predators": "Predators", "NSH": "Predators",
    "St. Louis Blues": "Blues", "STL": "Blues",
    "Winnipeg Jets": "Jets", "WPG": "Jets",
    "Minnesota Wild": "Wild", "MIN": "Wild",
    "Colorado Avalanche": "Avalanche", "COL": "Avalanche",
    "Dallas Stars": "Stars", "DAL": "Stars",
    "Vegas Golden Knights": "Golden Knights", "VGK": "Golden Knights",
    "Arizona Coyotes": "Coyotes", "ARI": "Coyotes",
    "Calgary Flames": "Flames", "CGY": "Flames",
    "Edmonton Oilers": "Oilers", "EDM": "Oilers",
    "Vancouver Canucks": "Canucks", "VAN": "Canucks",
    "Ottawa Senators": "Senators", "OTT": "Senators",
    "Buffalo Sabres": "Sabres", "BUF": "Sabres",
    "Seattle Kraken": "Kraken", "SEA": "Kraken",
    "San Jose Sharks": "Sharks", "SJS": "Sharks",
    "Anaheim Ducks": "Ducks", "ANA": "Ducks",
    "Los Angeles Kings": "Kings", "LAK": "Kings"
  },
  "mlb": {
    "New York Yankees": "Yankees", "NYY": "Yankees",
    "Boston Red Sox": "Red Sox", "BOS": "Red Sox",
    "Los Angeles Dodgers": "Dodgers", "LAD": "Dodgers",
    "Houston Astros": "Astros", "HOU": "Astros",
    "Atlanta Braves": "Braves", "ATL": "Braves",
    "Toronto Blue Jays": "Blue Jays", "TOR": "Blue Jays",
    "New York Mets": "Mets", "NYM": "Mets",
    "Philadelphia Phillies": "Phillies", "PHI": "Phillies",
    "Chicago Cubs": "Cubs", "CHC": "Cubs",
    "Chicago White Sox": "White Sox", "CHW": "White Sox",
    "St. Louis Cardinals": "Cardinals", "STL": "Cardinals",
    "San Francisco Giants": "Giants", "SFG": "Giants",
    "San Diego Padres": "Padres", "SDP": "Padres",
    "Seattle Mariners": "Mariners", "SEA": "Mariners",
    "Minnesota Twins": "Twins", "MIN": "Twins",
    "Cleveland Guardians": "Guardians", "CLE": "Guardians",
    "Detroit Tigers": "Tigers", "DET": "Tigers",
    "Kansas City Royals": "Royals", "KCR": "Royals",
    "Baltimore Orioles": "Orioles", "BAL": "Orioles",
    "Tampa Bay Rays": "Rays", "TBR": "Rays",
    "Miami Marlins": "Marlins", "MIA": "Marlins",
    "Colorado Rockies": "Rockies", "COL": "Rockies",
    "Arizona Diamondbacks": "Diamondbacks", "ARI": "Diamondbacks",
    "Oakland Athletics": "Athletics", "OAK": "Athletics",
    "Los Angeles Angels": "Angels", "LAA": "Angels",
    "Texas Rangers": "Rangers", "TEX": "Rangers",
    "Washington Nationals": "Nationals", "WSN": "Nationals",
    "Pittsburgh Pirates": "Pirates", "PIT": "Pirates",
    "Cincinnati Reds": "Reds", "CIN": "Reds",
    "Milwaukee Brewers": "Brewers", "MIL": "Brewers"
  },
  "epl": {
    "Manchester City FC": "Man City", "Manchester City": "Man City", "MCFC": "Man City",
    "Manchester United FC": "Man United", "Manchester United": "Man United",
    "Man Utd": "Man United", "MUFC": "Man United",
    "Arsenal FC": "Arsenal",
    "Chelsea FC": "Chelsea",
    "Liverpool FC": "Liverpool",
    "Tottenham Hotspur": "Spurs", "Tottenham": "Spurs", "THFC": "Spurs",
    "Newcastle United": "Newcastle",
    "Aston Villa": "Aston Villa", "Villa": "Aston Villa",
    "West Ham United": "West Ham",
    "Brighton & Hove Albion": "Brighton",
    "Brentford FC": "Brentford",
    "Fulham FC": "Fulham",
    "Crystal Palace": "Crystal Palace",
    "Wolverhampton Wanderers": "Wolves", "Wolves": "Wolves",
    "Everton FC": "Everton",
    "Nottingham Forest": "Nottm Forest", "Nott'm Forest": "Nottm Forest",
    "Leicester City": "Leicester",
    "Ipswich Town": "Ipswich",
    "Southampton FC": "Southampton",
    "AFC Bournemouth": "Bournemouth",
    "Luton Town": "Luton",
    "Burnley FC": "Burnley",
    "Sheffield United": "Sheffield Utd"
  }
}
```

### `polyedge/matching/normalizer.py`
```python
from __future__ import annotations
import json
from pathlib import Path

_ALIASES_PATH = Path(__file__).parent / "aliases.json"
with open(_ALIASES_PATH) as f:
    _ALIASES: dict[str, dict[str, str]] = json.load(f)

_LOWER: dict[str, dict[str, str]] = {
    sport: {k.lower(): v for k, v in mapping.items()}
    for sport, mapping in _ALIASES.items()
}

def normalize_team(name: str, sport: str) -> str:
    return _LOWER.get(sport.lower(), {}).get(name.lower(), name)
```

Run: `pytest tests/matching/test_normalizer.py -v` → 6 PASSED

```bash
git add polyedge/matching/ tests/matching/test_normalizer.py
git commit -m "feat: team normalizer + full aliases"
```

---

## Task 8 — Event matcher

### `tests/matching/test_matcher.py`
```python
from datetime import datetime, timezone, timedelta
import pytest
from polyedge.models import OddsLine, PolyMarket
from polyedge.matching.matcher import find_matching_odds

def _gd():
    return datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)

def _poly(yes="Lakers", no="Warriors", sport="nba", gd=None):
    return PolyMarket("0xabc", f"Will {yes} beat {no}?", "111", 0.65,
                      sport, yes, no, gd or _gd(), "https://polymarket.com/t")

def _line(t1="Lakers", t2="Warriors", sport="nba", gd=None, src="pinnacle"):
    return OddsLine(src, sport, "NBA", t1, t2, gd or _gd(), 1.85, 2.10,
                    datetime.now(timezone.utc))

def test_exact_match():
    r = find_matching_odds(_poly(), [_line()])
    assert r is not None
    assert r.team_is_home is True

def test_away_team_match():
    r = find_matching_odds(_poly(yes="Warriors", no="Lakers"), [_line(t1="Lakers", t2="Warriors")])
    assert r is not None
    assert r.team_is_home is False

def test_no_match_different_sport():
    assert find_matching_odds(_poly(sport="nba"), [_line(sport="nhl")]) is None

def test_no_match_date_too_far():
    assert find_matching_odds(_poly(), [_line(gd=_gd() + timedelta(hours=5))]) is None

def test_date_within_window():
    assert find_matching_odds(_poly(), [_line(gd=_gd() + timedelta(hours=3))]) is not None

def test_fuzzy_fallback():
    r = find_matching_odds(_poly(yes="LA Lakers", no="Golden St Warriors"), [_line()])
    assert r is not None

def test_multiple_sources():
    r = find_matching_odds(_poly(), [_line(src="pinnacle"), _line(src="stake")])
    assert r is not None
    assert len(r.matched_lines) == 2
```

Run: `pytest tests/matching/test_matcher.py -v` → confirm ImportError

### `polyedge/matching/matcher.py`
```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from rapidfuzz import fuzz
from polyedge.models import OddsLine, PolyMarket
from polyedge.matching.normalizer import normalize_team

_WINDOW = timedelta(hours=4)
_FUZZ_MIN = 85

@dataclass
class MatchResult:
    matched_lines: list[OddsLine]
    team_is_home: bool

def find_matching_odds(poly: PolyMarket, lines: list[OddsLine]) -> MatchResult | None:
    cy = normalize_team(poly.team_yes, poly.sport)
    cn = normalize_team(poly.team_no, poly.sport)
    matched, is_home = [], None
    for line in lines:
        if line.sport.lower() != poly.sport.lower():
            continue
        if abs(line.game_date - poly.game_date) > _WINDOW:
            continue
        c1 = normalize_team(line.team1, line.sport)
        c2 = normalize_team(line.team2, line.sport)
        ok, h = _match(cy, cn, c1, c2)
        if ok:
            matched.append(line)
            is_home = h
    return MatchResult(matched, is_home) if matched else None

def _match(yes, no, t1, t2):
    if yes == t1 and no == t2: return True, True
    if yes == t2 and no == t1: return True, False
    sh = min(fuzz.token_sort_ratio(yes, t1), fuzz.token_sort_ratio(no, t2))
    sa = min(fuzz.token_sort_ratio(yes, t2), fuzz.token_sort_ratio(no, t1))
    if sh >= _FUZZ_MIN and sh >= sa: return True, True
    if sa >= _FUZZ_MIN: return True, False
    return False, False
```

Run: `pytest tests/matching/test_matcher.py -v` → 7 PASSED

```bash
git add polyedge/matching/matcher.py tests/matching/test_matcher.py
git commit -m "feat: event matcher — exact + fuzzy + sport guard + date window"
```

---

## Task 9 — Base fetcher + Polymarket fetcher

### `polyedge/fetchers/base.py`
```python
from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
import httpx
from polyedge.models import OddsLine

class BaseFetcher(ABC):
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    @abstractmethod
    async def fetch(self, sports: list[str]) -> list[OddsLine]: ...

    async def _get_json(self, url: str, **kwargs) -> list | dict:
        last = None
        for i in range(3):
            try:
                r = await self.client.get(url, timeout=15.0, **kwargs)
                r.raise_for_status()
                return r.json()
            except Exception as e:
                last = e
                if i < 2: await asyncio.sleep(2 ** i)
        raise last
```

### `tests/fetchers/test_polymarket.py`
```python
import pytest, respx, httpx
from polyedge.fetchers.polymarket import PolymarketFetcher

MOCK = [
    {"id": "0xabc", "question": "Will the Lakers beat the Warriors on April 10?",
     "startDate": "2026-04-10T18:00:00Z", "endDate": "2026-04-11T04:00:00Z",
     "active": True, "closed": False, "outcomePrices": "[\"0.65\", \"0.35\"]",
     "tokens": [{"token_id": "111", "outcome": "Yes"}, {"token_id": "222", "outcome": "No"}],
     "tags": [{"label": "Sports", "slug": "sports"}, {"label": "NBA", "slug": "nba"}]},
    {"id": "0xdef", "question": "Will the Canadiens beat the Leafs on April 11?",
     "startDate": "2026-04-11T19:00:00Z", "endDate": "2026-04-12T03:00:00Z",
     "active": True, "closed": False, "outcomePrices": "[\"0.55\", \"0.45\"]",
     "tokens": [{"token_id": "333", "outcome": "Yes"}, {"token_id": "444", "outcome": "No"}],
     "tags": [{"label": "Sports", "slug": "sports"}, {"label": "NHL", "slug": "nhl"}]},
    {"id": "0xpol", "question": "Will crypto go up?",
     "startDate": "2026-04-12T00:00:00Z", "endDate": "2026-04-13T00:00:00Z",
     "active": True, "closed": False, "outcomePrices": "[\"0.70\", \"0.30\"]",
     "tokens": [{"token_id": "555", "outcome": "Yes"}, {"token_id": "666", "outcome": "No"}],
     "tags": [{"label": "Crypto", "slug": "crypto"}]},
]

@pytest.mark.asyncio
async def test_sports_only():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/markets").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba", "nhl"])
    assert len(markets) == 2
    assert {m.sport for m in markets} == {"nba", "nhl"}

@pytest.mark.asyncio
async def test_prices_parsed():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/markets").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba"])
    nba = markets[0]
    assert nba.price_yes == pytest.approx(0.65)
    assert nba.token_id_yes == "111"

@pytest.mark.asyncio
async def test_teams_extracted():
    with respx.mock:
        respx.get("https://gamma-api.polymarket.com/markets").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            markets = await PolymarketFetcher(c).fetch(["nba"])
    nba = markets[0]
    assert nba.team_yes == "Lakers"
    assert nba.team_no == "Warriors"
```

Run: `pytest tests/fetchers/test_polymarket.py -v` → confirm ImportError

### `polyedge/fetchers/polymarket.py`
```python
from __future__ import annotations
import asyncio, json as _json, re
from datetime import datetime, timezone
import httpx
from polyedge.models import PolyMarket
from polyedge.matching.normalizer import normalize_team

_BASE = "https://gamma-api.polymarket.com"
_WILL_BEAT = re.compile(
    r"Will (?:the )?(.+?) (?:beat|defeat|win (?:vs?\.?|against)) (?:the )?(.+?)(?:\s+on\b|\?|$)",
    re.IGNORECASE)
_VS = re.compile(r"^(.+?)\s+vs\.?\s+(.+?)(?:\s*[-–]|\?|$)", re.IGNORECASE)

class PolymarketFetcher:
    def __init__(self, client: httpx.AsyncClient):
        self.client = client

    async def fetch(self, sports: list[str]) -> list[PolyMarket]:
        data = await self._get(f"{_BASE}/markets",
                               params={"active": "true", "closed": "false", "limit": 500})
        return [m for item in data for m in [self._parse(item, sports)] if m]

    def _parse(self, item, sports) -> PolyMarket | None:
        tags = [t.get("slug", "").lower() for t in item.get("tags", [])]
        sport = next((t for t in tags if t in sports), None)
        if not sport: return None
        try:
            prices = item.get("outcomePrices", '["0.5","0.5"]')
            price_yes = float((_json.loads(prices) if isinstance(prices, str) else prices)[0])
        except Exception: return None
        tokens = item.get("tokens", [])
        tid = next((t["token_id"] for t in tokens if t.get("outcome") == "Yes"), None)
        if not tid: return None
        ty, tn = self._teams(item.get("question", ""), sport)
        if not ty or not tn: return None
        try:
            gd = datetime.fromisoformat(item["startDate"].replace("Z", "+00:00"))
        except Exception: return None
        slug = item.get("slug", item.get("id", ""))
        return PolyMarket(item["id"], item.get("question",""), tid, price_yes, sport,
                          normalize_team(ty, sport), normalize_team(tn, sport),
                          gd, f"https://polymarket.com/event/{slug}")

    def _teams(self, q, sport):
        m = _WILL_BEAT.search(q)
        if m: return m.group(1).strip(), m.group(2).strip()
        m = _VS.search(q)
        if m: return m.group(1).strip(), m.group(2).strip()
        return None, None

    async def _get(self, url, **kw):
        last = None
        for i in range(3):
            try:
                r = await self.client.get(url, timeout=15.0, **kw)
                r.raise_for_status(); return r.json()
            except Exception as e:
                last = e
                if i < 2: await asyncio.sleep(2 ** i)
        raise last
```

Run: `pytest tests/fetchers/test_polymarket.py -v` → 3 PASSED

```bash
git add polyedge/fetchers/ tests/fetchers/test_polymarket.py
git commit -m "feat: Polymarket Gamma API fetcher"
```

---

## Task 10 — Pinnacle fetcher

Pinnacle league IDs: NBA=487, NHL=1456, MLB=246, EPL=1980

### `tests/fetchers/test_pinnacle.py`
```python
import pytest, respx, httpx
from polyedge.fetchers.pinnacle import PinnacleFetcher

MOCK = {"matchups": [
    {"id": 1, "startTime": "2026-04-10T18:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Los Angeles Lakers", "alignment": "home"},
                      {"name": "Golden State Warriors", "alignment": "away"}],
     "periods": [{"number": 0, "moneyline": {"home": 1.85, "away": 2.10}}]},
    {"id": 2, "startTime": "2026-04-11T19:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Boston Celtics", "alignment": "home"},
                      {"name": "Miami Heat", "alignment": "away"}],
     "periods": [{"number": 0, "moneyline": {"home": 1.40, "away": 3.10}}]},
    {"id": 3, "startTime": "2026-04-10T20:00:00+00:00",
     "league": {"id": 487, "name": "NBA"},
     "participants": [{"name": "Dallas Mavericks", "alignment": "home"},
                      {"name": "Denver Nuggets", "alignment": "away"}],
     "periods": [{"number": 0}]},  # no moneyline — skip
]}

@pytest.mark.asyncio
async def test_returns_lines():
    with respx.mock:
        respx.get("https://www.pinnacle.com/api/v3/matchups").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "pinnacle" for l in lines)

@pytest.mark.asyncio
async def test_normalizes_teams():
    with respx.mock:
        respx.get("https://www.pinnacle.com/api/v3/matchups").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await PinnacleFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    assert g.odds_home == pytest.approx(1.85)
```

Run: `pytest tests/fetchers/test_pinnacle.py -v` → confirm ImportError

### `polyedge/fetchers/pinnacle.py`
```python
from __future__ import annotations
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

_BASE = "https://www.pinnacle.com/api/v3"
_LEAGUES: dict[str, list[int]] = {
    "nba": [487], "nhl": [1456], "mlb": [246], "epl": [1980],
}

class PinnacleFetcher(BaseFetcher):
    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        ids, by_lid = [], {}
        for s in sports:
            for lid in _LEAGUES.get(s.lower(), []):
                ids.append(lid); by_lid[lid] = s.lower()
        if not ids: return []
        data = await self._get_json(f"{_BASE}/matchups",
                                    params={"leagueIds": ",".join(str(i) for i in ids),
                                            "withSpecials": "false", "brandId": "1"})
        return [l for m in data.get("matchups", []) for l in [self._parse(m, by_lid)] if l]

    def _parse(self, m, by_lid) -> OddsLine | None:
        sport = by_lid.get(m.get("league", {}).get("id"))
        if not sport: return None
        ml = next((p["moneyline"] for p in m.get("periods", [])
                   if p.get("number") == 0 and "moneyline" in p), None)
        if not ml: return None
        parts = m.get("participants", [])
        home = next((p["name"] for p in parts if p.get("alignment") == "home"), None)
        away = next((p["name"] for p in parts if p.get("alignment") == "away"), None)
        if not home or not away: return None
        try:
            gd = datetime.fromisoformat(m["startTime"].replace("Z", "+00:00"))
        except Exception: return None
        return OddsLine("pinnacle", sport, m.get("league", {}).get("name", sport.upper()),
                        normalize_team(home, sport), normalize_team(away, sport),
                        gd, float(ml["home"]), float(ml["away"]), datetime.now(timezone.utc))
```

Run: `pytest tests/fetchers/test_pinnacle.py -v` → 2 PASSED

```bash
git add polyedge/fetchers/pinnacle.py tests/fetchers/test_pinnacle.py
git commit -m "feat: Pinnacle web API fetcher"
```

---

## Task 11 — Stake fetcher

### `tests/fetchers/test_stake.py`
```python
import pytest, respx, httpx
from polyedge.fetchers.stake import StakeFetcher

MOCK = {"data": {"sportsbookEventList": [
    {"id": "s1", "name": "Los Angeles Lakers vs Golden State Warriors",
     "startTime": "2026-04-10T18:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"name": "Match Winner",
                  "outcomes": [{"name": "Los Angeles Lakers", "price": 1.85},
                               {"name": "Golden State Warriors", "price": 2.10}]}]},
    {"id": "s2", "name": "Boston Celtics vs Miami Heat",
     "startTime": "2026-04-11T19:00:00.000Z",
     "sport": {"slug": "basketball_nba"},
     "markets": [{"name": "Match Winner",
                  "outcomes": [{"name": "Boston Celtics", "price": 1.40},
                               {"name": "Miami Heat", "price": 3.10}]}]},
]}}

@pytest.mark.asyncio
async def test_returns_lines():
    with respx.mock:
        respx.post("https://stake.com/_api/graphql").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    assert len(lines) == 2
    assert all(l.source == "stake" for l in lines)

@pytest.mark.asyncio
async def test_correct_odds():
    with respx.mock:
        respx.post("https://stake.com/_api/graphql").mock(
            return_value=httpx.Response(200, json=MOCK))
        async with httpx.AsyncClient() as c:
            lines = await StakeFetcher(c).fetch(["nba"])
    g = next(l for l in lines if "Lakers" in (l.team1, l.team2))
    assert g.team1 == "Lakers"
    assert g.odds_home == pytest.approx(1.85)
```

Run: `pytest tests/fetchers/test_stake.py -v` → confirm ImportError

### `polyedge/fetchers/stake.py`
```python
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

_URL = "https://stake.com/_api/graphql"
_SLUGS = {"basketball_nba": "nba", "ice_hockey_nhl": "nhl",
          "baseball_mlb": "mlb", "soccer_england_premier_league": "epl"}
_QUERY = """
query SportsbookEventList($sportSlug: String!, $limit: Int) {
  sportsbookEventList(sportSlug: $sportSlug, limit: $limit, status: UPCOMING) {
    id name startTime sport { slug }
    markets(name: "Match Winner") { name outcomes { name price } }
  }
}"""

class StakeFetcher(BaseFetcher):
    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        rev = {v: k for k, v in _SLUGS.items()}
        results = await asyncio.gather(
            *[self._sport(s, rev[s]) for s in sports if s in rev],
            return_exceptions=True)
        out = []
        for r in results:
            if isinstance(r, Exception): print(f"[stake] {r}")
            else: out.extend(r)
        return out

    async def _sport(self, sport, slug) -> list[OddsLine]:
        last = None
        for i in range(3):
            try:
                r = await self.client.post(_URL, json={"query": _QUERY,
                    "variables": {"sportSlug": slug, "limit": 200}},
                    timeout=15.0, headers={"Content-Type": "application/json"})
                r.raise_for_status()
                evs = r.json().get("data", {}).get("sportsbookEventList", [])
                return [l for e in evs for l in [self._parse(e, sport)] if l]
            except Exception as e:
                last = e
                if i < 2: await asyncio.sleep(2 ** i)
        raise last

    def _parse(self, ev, sport) -> OddsLine | None:
        mkt = next((m for m in ev.get("markets", []) if "winner" in m.get("name","").lower()), None)
        if not mkt: return None
        outs = mkt.get("outcomes", [])
        if len(outs) < 2: return None
        name = ev.get("name", "")
        parts = [p.strip() for p in name.split(" vs ")]
        rh, ra = (parts[0], parts[1]) if len(parts) == 2 else (outs[0]["name"], outs[1]["name"])
        try:
            gd = datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
        except Exception: return None
        return OddsLine("stake", sport, sport.upper(),
                        normalize_team(rh, sport), normalize_team(ra, sport),
                        gd, float(outs[0]["price"]), float(outs[1]["price"]),
                        datetime.now(timezone.utc))
```

Run: `pytest tests/fetchers/test_stake.py -v` → 2 PASSED

```bash
git add polyedge/fetchers/stake.py tests/fetchers/test_stake.py
git commit -m "feat: Stake GraphQL fetcher"
```

---

## Task 12 — Mise-o-jeu fetcher (Kambi)

No automated tests — Kambi client ID needs live verification.

### `polyedge/fetchers/miseonjeu.py`
```python
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import httpx
from polyedge.fetchers.base import BaseFetcher
from polyedge.models import OddsLine
from polyedge.matching.normalizer import normalize_team

# Verify: open miseonjeu.com → DevTools → Network → filter kambicdn.com
# Look for the path segment after /v2018/ — update this if wrong
_CLIENT = "lqmiseonjeu"
_BASE = f"https://eu-offering-api.kambicdn.com/offering/v2018/{_CLIENT}"
_SPORTS = {"nba": "basketball/nba", "nhl": "ice_hockey/nhl",
           "mlb": "baseball/mlb", "epl": "football/england/premier_league"}

class MiseonjeuFetcher(BaseFetcher):
    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        results = await asyncio.gather(
            *[self._sport(s) for s in sports if s in _SPORTS],
            return_exceptions=True)
        out = []
        for r in results:
            if isinstance(r, Exception): print(f"[miseonjeu] {r}")
            else: out.extend(r)
        return out

    async def _sport(self, sport) -> list[OddsLine]:
        path = _SPORTS[sport].replace("/", "_")
        url = f"{_BASE}/listView/{path}.json"
        for i in range(3):
            try:
                r = await self.client.get(url, params={"lang": "fr_CA", "market": "CA"},
                                          timeout=15.0)
                r.raise_for_status()
                return self._parse_response(r.json(), sport)
            except Exception as e:
                if i == 2: print(f"[miseonjeu] {sport} failed: {e}"); return []
                await asyncio.sleep(2 ** i)
        return []

    def _parse_response(self, data, sport) -> list[OddsLine]:
        return [l for ev in data.get("events", []) for l in [self._parse(ev, sport)] if l]

    def _parse(self, ev, sport) -> OddsLine | None:
        try:
            ed = ev.get("event", ev)
            name = ed.get("name", "")
            if " - " not in name: return None
            home_raw, away_raw = name.split(" - ", 1)
            gd = datetime.fromisoformat(ed.get("start", "").replace("Z", "+00:00"))
            bet_offers = ed.get("betOffers", [])
            offer = next((b for b in bet_offers
                         if b.get("betOfferType", {}).get("name", "") in
                         ("Match", "1X2", "Moneyline", "To Win")), None)
            if not offer: return None
            outs = offer.get("outcomes", [])
            ho = next((o for o in outs if o.get("label") in ("1","Home",home_raw.strip())), None)
            ao = next((o for o in outs if o.get("label") in ("2","Away",away_raw.strip())), None)
            if not ho or not ao: return None
            return OddsLine("miseonjeu", sport, sport.upper(),
                            normalize_team(home_raw.strip(), sport),
                            normalize_team(away_raw.strip(), sport),
                            gd, ho["odds"]/1000.0, ao["odds"]/1000.0,
                            datetime.now(timezone.utc))
        except Exception: return None
```

```bash
git add polyedge/fetchers/miseonjeu.py
git commit -m "feat: Mise-o-jeu Kambi fetcher (client ID needs live verification)"
```

---

## Task 13 — Scanner orchestrator

### `tests/test_scanner.py`
```python
from datetime import datetime, timezone
import pytest
from polyedge.models import OddsLine, PolyMarket
from polyedge.scanner import run_scan
from polyedge.config import Config, ScannerConfig
from polyedge.db.signals import get_signals

def _cfg():
    return Config(scanner=ScannerConfig(edge_threshold=0.05, bankroll=500.0, stale_odds_minutes=30),
                  sports=["nba"], sources={"pinnacle": True, "stake": True, "miseonjeu": False},
                  db_path=":memory:")

def _gd():
    return datetime(2026, 4, 10, 18, 0, tzinfo=timezone.utc)

def _poly(price=0.65):
    m = PolyMarket("0xabc","Will Lakers beat Warriors?","111",price,"nba",
                   "Lakers","Warriors",_gd(),"https://polymarket.com/t")
    return m

def _line(src="pinnacle", oh=1.70, oa=2.30):
    # oh=1.70,oa=2.30: fair_home≈0.575 → edge=0.65-0.575=0.075 > 5%
    return OddsLine(src,"nba","NBA","Lakers","Warriors",_gd(),oh,oa,datetime.now(timezone.utc))

@pytest.mark.asyncio
async def test_produces_signal(db):
    sigs = await run_scan([_poly()], [_line("pinnacle"), _line("stake")], _cfg(), db)
    assert len(sigs) == 1
    assert sigs[0].edge_pct > 0.05
    assert "pinnacle" in sigs[0].sources_used

@pytest.mark.asyncio
async def test_below_threshold_filtered(db):
    # fair=0.50, poly=0.51 → edge=0.01 < 5%
    poly = _poly(price=0.51)
    line = OddsLine("pinnacle","nba","NBA","Lakers","Warriors",_gd(),2.00,2.00,datetime.now(timezone.utc))
    sigs = await run_scan([poly], [line], _cfg(), db)
    assert len(sigs) == 0

@pytest.mark.asyncio
async def test_saves_to_db(db):
    await run_scan([_poly()], [_line()], _cfg(), db)
    saved = get_signals(db)
    assert len(saved) == 1
    assert saved[0].status == "pending"
```

Run: `pytest tests/test_scanner.py -v` → confirm ImportError

### `polyedge/scanner.py`
```python
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
```

Run: `pytest tests/test_scanner.py -v` → 3 PASSED

```bash
git add polyedge/scanner.py tests/test_scanner.py
git commit -m "feat: scanner orchestrator"
```

---

## Task 14 — CLI display

### `polyedge/cli/display.py`
```python
from __future__ import annotations
from rich.console import Console
from rich.table import Table
from rich import box
from polyedge.models import Signal

console = Console()

def print_signals_table(signals: list[Signal], title="PolyEdge Opportunities") -> None:
    if not signals:
        console.print("[yellow]No signals above threshold.[/yellow]"); return
    t = Table(title=title, box=box.ROUNDED, header_style="bold cyan")
    t.add_column("Sport", width=6)
    t.add_column("Matchup", min_width=28)
    t.add_column("Game Date", width=16)
    t.add_column("Edge %", justify="right", style="bold green")
    t.add_column("Poly Price", justify="right")
    t.add_column("Fair Value", justify="right")
    t.add_column("Sources", style="dim")
    t.add_column("Size ($)", justify="right", style="bold yellow")
    for s in sorted(signals, key=lambda x: x.edge_pct, reverse=True):
        t.add_row(s.sport.upper(), f"{s.team1} vs {s.team2}",
                  s.game_date.strftime("%b %d %H:%M"),
                  f"{s.edge_pct*100:.1f}%", f"{s.poly_price:.3f}",
                  f"{s.fair_value:.3f}", s.sources_used, f"${s.suggested_size:.2f}")
    console.print(t)

def print_pnl_table(pnl_by_sport: dict[str, float], total: float) -> None:
    t = Table(title="P&L by Sport", box=box.SIMPLE)
    t.add_column("Sport", style="bold")
    t.add_column("P&L ($)", justify="right")
    for sport, amt in sorted(pnl_by_sport.items()):
        c = "green" if amt >= 0 else "red"
        t.add_row(sport.upper(), f"[{c}]{amt:+.2f}[/{c}]")
    t.add_row("─"*8, "─"*10)
    c = "green" if total >= 0 else "red"
    t.add_row("[bold]TOTAL[/bold]", f"[bold {c}]{total:+.2f}[/bold {c}]")
    console.print(t)

def print_scan_summary(signals_found, markets_scanned, sources, duration_ms) -> None:
    console.print(f"[dim]Scanned {markets_scanned} markets · "
                  f"{signals_found} signal(s) · Sources: {', '.join(sources)} · {duration_ms}ms[/dim]")
```

```bash
git add polyedge/cli/display.py
git commit -m "feat: Rich CLI display"
```

---

## Task 15 — CLI commands

### `polyedge/cli/main.py`
```python
from __future__ import annotations
import asyncio, time
from typing import Optional
import httpx, typer
from rich.console import Console
from polyedge.config import load_config
from polyedge.db.schema import init_db
from polyedge.db.signals import get_signals, get_pnl_by_sport, resolve_signal, get_signal_by_id, log_scan
from polyedge.fetchers.polymarket import PolymarketFetcher
from polyedge.fetchers.pinnacle import PinnacleFetcher
from polyedge.fetchers.stake import StakeFetcher
from polyedge.fetchers.miseonjeu import MiseonjeuFetcher
from polyedge.scanner import run_scan
from polyedge.cli.display import print_signals_table, print_pnl_table, print_scan_summary

app = typer.Typer(help="PolyEdge — Polymarket arbitrage scanner")
console = Console()

def _load(cfg_path="config.toml"):
    cfg = load_config(cfg_path)
    return cfg, init_db(cfg.db_path)

@app.command()
def scan(config: str = typer.Option("config.toml")):
    """Run one scan and show opportunities."""
    asyncio.run(_do_scan(config))

@app.command()
def watch(config: str = typer.Option("config.toml")):
    """Continuously scan on the configured interval. Ctrl+C to stop."""
    cfg = load_config(config)
    ivl = cfg.scanner.scan_interval_minutes * 60
    console.print(f"[cyan]Scanning every {cfg.scanner.scan_interval_minutes}min. Ctrl+C to stop.[/cyan]")
    try:
        while True:
            asyncio.run(_do_scan(config))
            console.print(f"[dim]Next scan in {cfg.scanner.scan_interval_minutes}min…[/dim]")
            time.sleep(ivl)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped.[/yellow]")

@app.command()
def signals(
    sport: Optional[str] = typer.Option(None),
    min_edge: float = typer.Option(0.0),
    status: Optional[str] = typer.Option(None),
    config: str = typer.Option("config.toml"),
):
    """List signals from DB."""
    cfg, conn = _load(config)
    rows = get_signals(conn, sport=sport, min_edge=min_edge, status=status)
    if not rows: console.print("[yellow]No signals.[/yellow]"); return
    print_signals_table(rows, f"Signals (n={len(rows)})")

@app.command()
def pnl(config: str = typer.Option("config.toml")):
    """P&L summary by sport."""
    _, conn = _load(config)
    by_sport = get_pnl_by_sport(conn)
    if not by_sport: console.print("[yellow]No resolved signals yet.[/yellow]"); return
    print_pnl_table(by_sport, sum(by_sport.values()))

@app.command()
def resolve(
    signal_id: int = typer.Argument(),
    outcome: str = typer.Argument(),
    outcome_price: float = typer.Option(0.0),
    config: str = typer.Option("config.toml"),
):
    """Mark signal as won/lost/push."""
    if outcome not in ("won","lost","push"):
        console.print("[red]outcome must be: won / lost / push[/red]"); raise typer.Exit(1)
    _, conn = _load(config)
    resolve_signal(conn, signal_id, outcome, outcome_price)
    s = get_signal_by_id(conn, signal_id)
    c = "green" if s.pnl >= 0 else "red"
    console.print(f"Signal {signal_id} → {outcome} | P&L: [{c}]{s.pnl:+.2f}[/{c}]")

async def _do_scan(cfg_path: str) -> None:
    cfg, conn = _load(cfg_path)
    t0 = time.monotonic()
    active = [k for k, v in cfg.sources.items() if v]
    fetchers = {"pinnacle": PinnacleFetcher, "stake": StakeFetcher, "miseonjeu": MiseonjeuFetcher}
    async with httpx.AsyncClient(headers={"User-Agent": "PolyEdge/1.0"}) as client:
        poly_task = asyncio.create_task(PolymarketFetcher(client).fetch(cfg.sports))
        sb_tasks = {n: asyncio.create_task(fetchers[n](client).fetch(cfg.sports))
                    for n in active if n in fetchers}
        poly_markets = await poly_task
        odds_lines = []
        for n, task in sb_tasks.items():
            try: odds_lines.extend(await task)
            except Exception as e: console.print(f"[red][{n}] {e}[/red]")
    sigs = await run_scan(poly_markets, odds_lines, cfg, conn)
    ms = int((time.monotonic() - t0) * 1000)
    print_signals_table(sigs)
    print_scan_summary(len(sigs), len(poly_markets), active, ms)
    log_scan(conn, len(poly_markets), len(sigs), active, ms)
```

```bash
git add polyedge/cli/main.py
git commit -m "feat: Typer CLI — scan, watch, signals, pnl, resolve"
```

---

## Task 16 — Smoke test + final verification

### Run all tests
```bash
pytest -v
```
All tests must pass before proceeding.

### Run live scan
```bash
python main.py scan
```
Expected: Rich table (possibly empty if no signals above threshold) + scan summary line.

### Verify Mise-o-jeu Kambi client ID
```bash
python -c "
import asyncio, httpx
from polyedge.fetchers.miseonjeu import MiseonjeuFetcher
async def t():
    async with httpx.AsyncClient() as c:
        lines = await MiseonjeuFetcher(c).fetch(['nba'])
        print(f'Mise-o-jeu: {len(lines)} lines')
asyncio.run(t())
"
```
If 0 lines with an error: open miseonjeu.com in browser → DevTools → Network → filter `kambicdn` → note the path after `/v2018/` → update `_CLIENT` in `polyedge/fetchers/miseonjeu.py`.

### Test watch mode (one cycle)
```bash
python main.py watch
```
Let it complete one scan, verify it prints summary and schedules next.

### Final commit
```bash
git add .
git commit -m "feat: PolyEdge MVP — working scanner ready for paper trading"
```

---

## Paper trading instructions (after scanner is running)

1. Run `python main.py watch` — leave it running
2. Each scan auto-saves signals to `polyedge.db` as `status=pending`
3. After a game resolves, check the Polymarket URL in the signal
4. Run: `python main.py resolve <id> won` or `python main.py resolve <id> lost`
5. Run: `python main.py pnl` to see cumulative results by sport
6. Run: `python main.py signals --status pending` to see open positions

---

## Done criteria
- All `pytest -v` tests pass
- `python main.py scan` runs without crashing
- `python main.py watch` scans continuously
- Signals appear in DB after scan
- `python main.py pnl` works after resolving a signal
