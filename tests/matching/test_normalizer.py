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