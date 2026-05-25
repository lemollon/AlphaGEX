import datetime as dt
from backtest.blaze_gex_0dte.fullboard_cli import parse_args

def test_parse_args_defaults_cap_at_orat_end():
    ns = parse_args([])
    assert ns.start == dt.date(2023, 1, 3)
    assert ns.end == dt.date(2025, 12, 5)   # ORAT EOD chains end here
    assert ns.pts == [20, 30, 50]
    assert ns.sls == [30, 50, 100]

def test_parse_args_overrides():
    ns = parse_args(["--start", "2024-01-01", "--end", "2024-12-31", "--pts", "20", "--sls", "100"])
    assert ns.start == dt.date(2024, 1, 1)
    assert ns.pts == [20]
    assert ns.sls == [100]
