def quarter_kelly_size(edge_pct: float, fair_value: float, bankroll: float) -> tuple[float, float]:
    if edge_pct <= 0:
        raise ValueError("edge_pct must be positive")
    full_kelly = edge_pct / (1.0 - fair_value)
    quarter = full_kelly / 4.0
    size = max(min(quarter * bankroll, bankroll), 1.0)
    return round(size, 2), round(quarter, 6)