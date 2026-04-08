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