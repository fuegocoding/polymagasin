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