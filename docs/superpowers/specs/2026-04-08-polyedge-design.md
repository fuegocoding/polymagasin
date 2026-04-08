# PolyEdge — Design Spec
**Date:** 2026-04-08  
**Status:** Approved  
**Goal:** Polymarket ↔ sportsbook arbitrage scanner for paper trading. Detects ≥5% edge opportunities, logs all signals to SQLite, outputs CLI table. No auto-execution in MVP.

---

## 1. Scope

**In:** Scanner, event matching, edge calculation, SQLite signal tracking, CLI output, paper trading P&L.  
**Out:** Auto-execution (CLOB orders), Telegram alerts, web UI. These are Phase 2+.

**Odds sources (priority order):**
1. Pinnacle — `api.pinnacle.com` free REST API (sharpest lines, primary)
2. Stake — REST/GraphQL API
3. Mise-o-jeu — Kambi provider REST endpoints (investigate during impl; stub if unstable)

**Prediction market:** Polymarket Gamma API (`gamma-api.polymarket.com`, free, no auth)

**Sports:** NBA, NHL, MLB, EPL — driven by config

---

## 2. Package Structure

```
polyedge/
  config.py              # TOML config loader + defaults
  models.py              # Dataclasses: OddsLine, PolyMarket, Signal, ScanResult
  scanner.py             # Orchestrates one full scan cycle
  fetchers/
    base.py              # Abstract BaseFetcher: async def fetch() -> list[OddsEvent]
    polymarket.py        # Polymarket Gamma API
    pinnacle.py          # Pinnacle free API
    stake.py             # Stake sportsbook API
    miseonjeu.py         # Mise-o-jeu via Kambi provider endpoints
  matching/
    normalizer.py        # Team name → canonical form
    matcher.py           # Event matching: sport + date(±4h) + team pair + rapidfuzz fallback
    aliases.json         # {sport: {alias: canonical}} mappings
  edge/
    calculator.py        # Devig (multiplicative), implied prob, edge %, fair value
    kelly.py             # Quarter-Kelly sizing given edge % and bankroll
  db/
    schema.py            # SQLite init, table creation
    signals.py           # Signal insert, query, update (CRUD)
  cli/
    main.py              # Typer app entry point
    display.py           # Rich table formatting for scan results
config.toml              # User-editable: sports, threshold, bankroll, API keys
requirements.txt
```

---

## 3. Core Data Models (`models.py`)

```python
@dataclass
class OddsLine:
    source: str           # "pinnacle" | "stake" | "miseonjeu"
    sport: str
    league: str
    team1: str            # canonical home team
    team2: str            # canonical away team
    game_date: datetime
    odds_home: float      # American or decimal (normalized to decimal internally)
    odds_away: float
    fetched_at: datetime

@dataclass
class PolyMarket:
    market_id: str
    question: str
    token_id_yes: str
    price_yes: float      # 0.0–1.0 implied probability
    sport: str
    team_yes: str         # canonical team this YES token represents
    team_no: str
    game_date: datetime
    url: str

@dataclass
class Signal:
    id: int | None
    timestamp: datetime
    sport: str
    league: str
    team1: str
    team2: str
    game_date: datetime
    edge_pct: float
    poly_price: float
    poly_market_id: str
    fair_value: float        # deviggged consensus probability
    kelly_fraction: float
    suggested_size: float    # quarter-Kelly * bankroll
    sources_used: str        # comma-separated: "pinnacle,stake"
    status: str              # "pending" | "won" | "lost" | "push"
    outcome_price: float | None
    pnl: float | None
```

---

## 4. Fetcher Interface (`fetchers/base.py`)

Each fetcher implements:
```python
class BaseFetcher(ABC):
    @abstractmethod
    async def fetch(self, sports: list[str]) -> list[OddsLine]:
        ...
```

All fetchers use a shared `httpx.AsyncClient` passed in at construction. Exponential backoff on 429/5xx (3 retries, 1s/2s/4s delays).

---

## 5. Event Matching

**Pipeline:**
1. Normalize all team names via `aliases.json` lookups per sport
2. For each PolyMarket, find OddsLines where:
   - Same sport
   - game_date within ±4 hours
   - Both teams match canonically
3. Fallback: if canonical match fails, try rapidfuzz `token_sort_ratio` ≥85 on team names
4. Cross-sport guard: never match across sport boundaries
5. Log all matches (including low-confidence fuzzy) to `scan_logs` for audit

**`aliases.json` structure:**
```json
{
  "nba": {"LA Lakers": "Lakers", "Los Angeles Lakers": "Lakers", ...},
  "nhl": {"MTL": "Canadiens", "Montreal Canadiens": "Canadiens", ...},
  "soccer": {"FC Barcelona": "Barcelona", "Barça": "Barcelona", ...}
}
```

---

## 6. Edge Calculation

**Devig (multiplicative method):**
```
implied_home = 1 / decimal_odds_home
implied_away = 1 / decimal_odds_away
overround = implied_home + implied_away
fair_home = implied_home / overround
fair_away = implied_away / overround
```

If multiple sportsbook sources are available, average their fair values (equal weight for MVP; Pinnacle-weighted in Phase 2).

**Edge:**
```
edge = poly_price_yes - fair_value_team_yes
```
Signal is generated only when `edge >= threshold` (default 5%).

**Quarter-Kelly sizing:**
```
kelly_fraction = edge / (1 - fair_value)
quarter_kelly = kelly_fraction / 4
suggested_size = quarter_kelly * bankroll
```

---

## 7. Database Schema (SQLite)

```sql
CREATE TABLE signals (
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
);

CREATE TABLE scan_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT NOT NULL,
    markets_scanned  INTEGER NOT NULL,
    signals_found    INTEGER NOT NULL,
    sources_active   TEXT NOT NULL,
    duration_ms      INTEGER NOT NULL
);
```

---

## 8. CLI Commands

| Command | Behavior |
|---|---|
| `polyedge scan` | Run one scan cycle, print Rich table of signals, save to DB |
| `polyedge watch` | Loop scan every 30min (configurable), Ctrl+C to stop |
| `polyedge signals [--sport NBA] [--min-edge 5]` | Query and display signals from DB |
| `polyedge pnl` | P&L summary table grouped by sport |
| `polyedge resolve <id> <won\|lost\|push>` | Record outcome, compute P&L vs suggested_size |

**Scan output table columns:** Sport · Matchup · Game Date · Edge% · Poly Price · Fair Value · Sources · Suggested Size ($)

---

## 9. Config (`config.toml`)

```toml
[scanner]
edge_threshold = 0.05     # minimum edge to generate signal
scan_interval_minutes = 30
stale_odds_minutes = 30
bankroll = 500.0          # paper trading bankroll in USD

[sports]
enabled = ["nba", "nhl", "mlb", "epl"]

[sources]
pinnacle = true
stake = true
miseonjeu = true

[db]
path = "polyedge.db"

# API keys (if needed)
[keys]
# stake_api_key = ""
# telegram_token = ""
# telegram_chat_id = ""
```

---

## 10. Error Handling

- Each fetcher failure is isolated — a failed source is skipped, others continue
- Stale odds (fetched_at > 30min) are filtered before edge calculation
- All fetch errors logged to stderr with source name
- Minimum 2 sources required for a signal (at least Pinnacle + one other), else skip
- Scanner never crashes on bad data — log and continue

---

## 11. Mise-o-jeu Implementation Note

Mise-o-jeu (Loto-Québec) likely uses Kambi as their betting engine. Kambi exposes REST endpoints like:
```
https://eu-offering-api.kambicdn.com/offering/v2018/{client}/listView/football.json
```
The client ID for Mise-o-jeu needs to be confirmed by inspecting network requests on miseonjeu.com. If Kambi endpoints are confirmed, the fetcher hits them directly (no scraping). If not, the fetcher is stubbed with a clear `NotImplementedError` and excluded from the active sources.

---

## 12. Paper Trading Flow

1. Run `polyedge watch` for several days
2. All signals auto-saved as `status='pending'` with `suggested_size` calculated
3. After game resolves, check Polymarket resolution price manually (or via Gamma API)
4. Run `polyedge resolve <id> won` — computes `pnl = suggested_size * (1/poly_price - 1)` for wins, `pnl = -suggested_size` for losses
5. Run `polyedge pnl` to see cumulative results by sport

This gives a real-time paper trading dataset within a few days of running.
