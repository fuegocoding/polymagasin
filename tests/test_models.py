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