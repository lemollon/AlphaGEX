from backtest.directional_1dte.config import BOT_CONFIGS, SOLOMON, GIDEON


def test_solomon_matches_live_production():
    assert SOLOMON.name == "solomon"
    assert SOLOMON.ticker == "SPY"
    assert SOLOMON.wall_filter_pct == 1.0
    assert SOLOMON.spread_width == 2
    assert SOLOMON.min_vix == 12.0
    assert SOLOMON.max_vix == 35.0
    assert SOLOMON.risk_per_trade == 1000.0
    assert SOLOMON.starting_capital == 100000.0


def test_gideon_matches_live_production():
    assert GIDEON.name == "gideon"
    assert GIDEON.spread_width == 3
    assert GIDEON.max_vix == 30.0  # tighter than SOLOMON


def test_bot_configs_dict():
    assert set(BOT_CONFIGS.keys()) == {"solomon", "gideon"}
    assert BOT_CONFIGS["solomon"] is SOLOMON
    assert BOT_CONFIGS["gideon"] is GIDEON
