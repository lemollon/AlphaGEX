from backend.bots.registry import BOT_REGISTRY, get_bot, list_bots


def test_bots_registered():
    assert set(BOT_REGISTRY.keys()) == {"surge", "splash", "tide", "drift", "flow", "meadow", "undertow", "delta"}


def test_splash_defaults():
    # SPLASH v2 (2026-07-09) — SPX 0DTE long butterfly ONLY on the real-fill
    # validated RIVER config: morning entry, hold to the 14:45 CT close,
    # no PT ladder (pt 1.0 = unreachable), no SL (3.0 = unreachable),
    # one entry per day, $10k paper account. SPX per operator decision
    # (SPXW root, cash-settled, ~$1,000-1,200 debit/lot -> bp 0.20 = 1-2 lots).
    b = get_bot("splash")
    assert b["strategy"] == "long_butterfly"
    assert b["ticker"] == "SPX"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["one_entry_per_day"] is True
    assert b["pt_ladder"] is False
    assert b["defaults"]["starting_capital"] == 10000.0
    assert b["defaults"]["bp_pct"] == 0.20
    assert b["defaults"]["sd_mult"] == 1.0
    assert b["defaults"]["pt_pct"] == 1.0
    assert b["defaults"]["sl_pct"] == 3.0
    assert b["defaults"]["max_contracts"] == 4
    assert b["defaults"]["entry_end_ct"] == "10:00"
    assert b["defaults"]["enabled"] is True


def test_surge_defaults():
    # SURGE — pin+drift combo (long butterfly + two 0DTE/1DTE calendars).
    # Replaced BREEZE (which was just RIVER's pin bet as a credit — redundant).
    b = get_bot("surge")
    assert b["strategy"] == "pin_drift_combo"
    assert b["front_dte"] == 0
    assert b["back_dte"] == 1          # 1DTE back legs for the calendars
    # 2026-07-03 sweep-validated shape: PT at 50% of max profit, NO stop,
    # wing 1.15x straddle (sd_mult 1.35 x 0.85), calendars +/- $2.
    # sl_pct 3.0 (2026-07-09): 1.0 was meant as "no stop" but fired on
    # phantom negative marks from missing leg quotes (-$888 on 7/7); 3.0 is
    # genuinely unreachable for a defined-risk debit combo.
    assert b["defaults"]["pt_pct"] == 0.50
    assert b["defaults"]["sl_pct"] == 3.0
    assert b["defaults"]["sd_mult"] == 1.35
    assert b["defaults"]["drift_offset"] == 2
    assert b["defaults"]["eod_close_ct"] == "14:45"
    # Quarter-Kelly at half-spread fills (2026-07-03 study); the old 0.50 was
    # ~1.3x FULL Kelly and drove the live paper drawdown.
    assert b["defaults"]["bp_pct"] == 0.10
    assert b["defaults"]["max_contracts"] == 0
    # Shipped LIVE (paper) 2026-06-24 — enabled by default like RIVER.
    assert b["defaults"]["enabled"] is True


def test_tide_defaults():
    b = get_bot("tide")
    assert b["strategy"] == "double_calendar"
    # Restructured 2026-06-24 (backtest): 7/30 DTE + strikes at 1.5x straddle.
    assert b["front_dte"] == 7
    assert b["back_dte"] == 30
    assert b["defaults"]["strike_mult"] == 1.5
    assert b["defaults"]["pt_pct"] == 0.50
    # sl_pct 3.0 = effectively no stop (hold to expiry); backtest showed the
    # stop only ever loses money (fires intraday, sells recoverable dips).
    assert b["defaults"]["sl_pct"] == 3.0
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


def test_get_bot_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        get_bot("nope")


def test_list_bots_returns_keys():
    assert sorted(list_bots()) == ["delta", "drift", "flow", "meadow", "splash", "surge", "tide", "undertow"]


def test_undertow_registered():
    from backend.bots.registry import get_bot
    meta = get_bot("undertow")
    assert meta["display"] == "UNDERTOW"
    assert meta["strategy"] == "vertical_debit"
    assert "SPY" in meta["universe"] and "NVDA" in meta["universe"]
    assert meta["params"]["lookback_n"] == 5
    assert meta["defaults"]["enabled"] is False
    assert meta["defaults"]["max_concurrent_positions"] == 5


def test_undertow_is_vertical_debit():
    from backend.bots.registry import get_bot
    m = get_bot("undertow")
    assert m["vertical_mode"] == "debit"
    assert m["params"]["spread_pct"] == 0.04
    assert m["defaults"]["pt_pct"] == 0.50 and m["defaults"]["sl_pct"] == 0.50


def test_undertow_tables_autocreate(db_session):
    # create_bot_tables ran in the fixture; the config row must be seeded.
    from sqlalchemy import text
    eng = db_session.get_bind()
    row = eng.connect().execute(
        text("SELECT enabled, bp_pct FROM undertow_config WHERE id=1")
    ).mappings().first()
    assert row is not None
    assert bool(row["enabled"]) is False


def test_delta_registered_credit(db_session):
    from backend.bots.registry import get_bot
    from sqlalchemy import text
    m = get_bot("delta")
    assert m["display"] == "DELTA" and m["vertical_mode"] == "credit"
    assert m["params"]["min_credit"] == 0.20
    assert m["defaults"]["enabled"] is False and m["defaults"]["sl_pct"] == 1.5
    eng = db_session.get_bind()
    row = eng.connect().execute(text("SELECT enabled FROM delta_config WHERE id=1")).first()
    assert row is not None
