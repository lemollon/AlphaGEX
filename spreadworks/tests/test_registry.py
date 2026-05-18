from backend.bots.registry import BOT_REGISTRY, get_bot, list_bots


def test_three_bots_registered():
    assert set(BOT_REGISTRY.keys()) == {"frost", "tide", "drift"}


def test_frost_defaults():
    b = get_bot("frost")
    assert b["strategy"] == "iron_butterfly"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["defaults"]["pt_pct"] == 0.30
    assert b["defaults"]["sl_pct"] == 2.0
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["eod_close_ct"] == "14:45"


def test_tide_defaults():
    b = get_bot("tide")
    assert b["strategy"] == "double_calendar"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["pt_pct"] == 0.50
    assert b["defaults"]["sl_pct"] == 1.0


def test_drift_defaults():
    b = get_bot("drift")
    assert b["strategy"] == "double_diagonal"
    assert b["front_dte"] == 1
    assert b["back_dte"] == 14
    assert b["defaults"]["delta_skew"] == 0


def test_get_bot_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_bot("nope")


def test_list_bots_returns_keys():
    assert sorted(list_bots()) == ["drift", "frost", "tide"]
