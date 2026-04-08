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