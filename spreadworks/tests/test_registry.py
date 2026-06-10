from backend.bots.registry import BOT_REGISTRY, get_bot, list_bots


def test_bots_registered():
    assert set(BOT_REGISTRY.keys()) == {"breeze", "tide", "drift", "flow", "meadow", "river", "undertow"}


def test_breeze_defaults():
    b = get_bot("breeze")
    assert b["strategy"] == "iron_butterfly"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["defaults"]["pt_pct"] == 0.30
    assert b["defaults"]["sl_pct"] == 2.0
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["eod_close_ct"] == "14:45"
    # All bots deploy 50% of the account, uncapped — matches FLOW.
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0


def test_tide_defaults():
    b = get_bot("tide")
    assert b["strategy"] == "double_calendar"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["pt_pct"] == 0.50
    assert b["defaults"]["sl_pct"] == 1.0
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0


def test_drift_defaults():
    b = get_bot("drift")
    assert b["strategy"] == "double_diagonal"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["delta_skew"] == 0
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0


def test_flow_defaults():
    """FLOW mirrors SPARK criteria: SD=1.2, PT=30%, SL=50% of max profit."""
    b = get_bot("flow")
    assert b["strategy"] == "iron_condor"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 1
    assert b["back_dte"] is None
    assert b["defaults"]["sd_mult"] == 1.2
    assert b["defaults"]["pt_pct"] == 0.30
    assert b["defaults"]["sl_pct"] == 0.50
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0
    assert b["defaults"]["entry_start_ct"] == "08:30"


def test_meadow_defaults():
    """MEADOW — credit double diagonal, the credit-side sibling of DRIFT."""
    b = get_bot("meadow")
    assert b["strategy"] == "double_diagonal_credit"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 6
    assert b["back_dte"] == 9
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["pt_pct"] == 0.50
    assert b["defaults"]["sl_pct"] == 1.0
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0
    assert b["defaults"]["enabled"] is True
    # Enters Mondays and Fridays only.
    assert b["defaults"]["entry_days"] == "mon,fri"


def test_river_defaults():
    """RIVER — long (debit) butterfly, the debit-side sibling of BREEZE."""
    b = get_bot("river")
    assert b["strategy"] == "long_butterfly"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["pt_pct"] == 0.30
    assert b["defaults"]["sl_pct"] == 0.50
    assert b["defaults"]["bp_pct"] == 0.50
    assert b["defaults"]["max_contracts"] == 0
    assert b["defaults"]["enabled"] is True
    assert b["defaults"]["eod_close_ct"] == "14:45"


def test_get_bot_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_bot("nope")


def test_list_bots_returns_keys():
    assert sorted(list_bots()) == ["breeze", "drift", "flow", "meadow", "river", "tide", "undertow"]


def test_undertow_registered():
    from backend.bots.registry import get_bot
    meta = get_bot("undertow")
    assert meta["display"] == "UNDERTOW"
    assert meta["strategy"] == "dip_buy"
    assert "SPY" in meta["universe"] and "NVDA" in meta["universe"]
    assert meta["params"]["lookback_n"] == 5
    assert meta["defaults"]["enabled"] is False
    assert meta["defaults"]["max_concurrent_positions"] == 5


def test_undertow_tables_autocreate(db_session):
    # create_bot_tables ran in the fixture; the config row must be seeded.
    from sqlalchemy import text
    eng = db_session.get_bind()
    row = eng.connect().execute(
        text("SELECT enabled, bp_pct FROM undertow_config WHERE id=1")
    ).mappings().first()
    assert row is not None
    assert bool(row["enabled"]) is False
