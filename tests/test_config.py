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