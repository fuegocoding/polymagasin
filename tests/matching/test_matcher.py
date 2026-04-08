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