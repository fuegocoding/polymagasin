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