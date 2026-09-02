from backend.bots.registry import BOT_REGISTRY, get_bot, list_bots


def test_bots_registered():
    assert set(BOT_REGISTRY.keys()) == {"surge", "splash", "ripple", "tide", "drift", "flow", "meadow", "undertow",
         "delta", "ebb", "ebb_pm", "updraft", "backdraft", "reversal", "embreach", "embreachq",
         "afterburn", "weekender", "flashpoint", "thermal", "wildfire",
         "afterglow", "ember", "squall", "tempest"}


def test_ripple_defaults():
    # RIPPLE — SPLASH's live A/B twin (2026-07-09): same SPX 0DTE fly and
    # entry rules, but the fly_bt.py sweep winner: wing sd 1.5 and HOLD TO
    # CASH SETTLEMENT (no 14:45 buyback — that exit forfeits the edge).
    b = get_bot("ripple")
    assert b["strategy"] == "long_butterfly"
    assert b["ticker"] == "SPX"
    assert b["one_entry_per_day"] is True
    assert b["pt_ladder"] is False
    assert b["settle_at_expiry"] is True
    assert b["compare_with"] == "splash"
    assert b["defaults"]["sd_mult"] == 1.5
    assert b["defaults"]["max_contracts"] == 1
    assert b["defaults"]["bp_pct"] == 0.25
    assert b["defaults"]["pt_pct"] == 1.0
    assert b["defaults"]["sl_pct"] == 3.0
    assert b["defaults"]["starting_capital"] == 10000.0
    assert b["defaults"]["enabled"] is True


def test_splash_defaults():
    # SPLASH v2.1 (2026-07-09) — XSP (Mini-SPX) twin of RIPPLE: the IDENTICAL
    # validated fly strategy (wing sd 1.5, one morning entry, hold to cash
    # settlement) at 1/10 contract size (~$200/lot). bp 0.10 / max 5 lots =
    # the affordable-sizing tier of the vehicle A/B.
    b = get_bot("splash")
    assert b["strategy"] == "long_butterfly"
    assert b["ticker"] == "XSP"
    assert b["front_dte"] == 0
    assert b["back_dte"] is None
    assert b["one_entry_per_day"] is True
    assert b["pt_ladder"] is False
    assert b["settle_at_expiry"] is True
    assert b["compare_with"] == "ripple"
    assert b["defaults"]["starting_capital"] == 10000.0
    assert b["defaults"]["bp_pct"] == 0.10
    assert b["defaults"]["sd_mult"] == 1.5
    assert b["defaults"]["pt_pct"] == 1.0
    assert b["defaults"]["sl_pct"] == 3.0
    assert b["defaults"]["max_contracts"] == 5
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
    assert sorted(list_bots()) == ["afterburn", "afterglow", "backdraft", "delta", "drift", "ebb", "ebb_pm", "ember",
         "embreach", "embreachq", "flashpoint", "flow", "meadow", "reversal",
         "ripple", "splash", "squall", "surge", "tempest", "thermal", "tide",
         "undertow", "updraft", "weekender", "wildfire"]


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


def test_ebb_defaults(db_session):
    # EBB — validated 0DTE SPY put credit spread (registry #23b). Single-
    # ticker fixed direction: strategy IS the kind (bull_put_spread), not the
    # DELTA/UNDERTOW universe marker.
    from backend.bots.registry import get_bot
    from sqlalchemy import text
    b = get_bot("ebb")
    assert b["display"] == "Ebb"
    assert b["strategy"] == "bull_put_spread"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 0
    assert b["back_dte"] == 0
    assert b["one_entry_per_day"] is True
    assert b["settle_at_expiry"] is True
    # 🚨 SPARK's structure, NOT FLAME's. The AM (10:05) and PM (13:05) clocks
    # are two different walk-forward cells: spot-$2/$5 for the AM clock,
    # spot-$1/$2 for the PM clock. The 8/15 "share a spec" restructure put
    # FLAME's structure at SPARK's clock (the worst AM cell); restored 9/2 to
    # match the live scanner's 8/27 fix.
    assert b["params"]["short_otm_abs"] == 2.0
    assert b["params"]["spread_abs"] == 5.0
    assert b["params"]["min_credit"] == 0.10
    # The $5-wing bands, pre-registered 8/13 off #23b's own 930-day stream.
    bands = b["health_bands"]
    assert bands["watch_roll60"] == -524.0
    assert bands["demote_roll60"] == -1216.0
    assert bands["demote_roll120"] == 0.0
    assert bands["min_credit20"] == 30.0
    # Carries the VIX decay gate too — ungated this tranche is t=+1.25.
    assert b["defaults"]["vix_decay_max"] == 0.90
    d = b["defaults"]
    assert d["starting_capital"] == 3000.0
    assert d["enabled"] is False        # no bot ships armed
    assert d["max_contracts"] == 1
    assert d["max_concurrent_positions"] == 1
    assert d["entry_start_ct"] == "10:05"
    assert d["entry_end_ct"] == "10:20"

    eng = db_session.get_bind()
    row = eng.connect().execute(text("SELECT enabled FROM ebb_config WHERE id=1")).mappings().first()
    assert row is not None
    assert bool(row["enabled"]) is False


def test_ebb_discord_routes_to_risk_channel():
    # EBB posts opens/settles to the risk-advisor channel, not the generic
    # fleet webhook (2026-08-13) — discord_alerts must be on and the
    # webhook-override key must point at the risk env var.
    from backend.bots.registry import get_bot
    b = get_bot("ebb")
    assert b["defaults"]["discord_alerts"] is True
    assert b["discord_webhook_env"] == "RISK_ADVISOR_DISCORD_WEBHOOK"


def test_ebb_pm_defaults(db_session):
    # EBB PM — validated afternoon tranche of EBB (registry #41/#42,
    # 2026-08-13), RESTRUCTURED 2026-08-15 by the 0DTE structure sweep to
    # short spot-$1 / $2 wing. Same $/contract at this clock on a clean engine
    # ($4.60 vs $4.80) on 40% of the capital at risk, and it now carries the
    # vix_decay_max gate.
    from backend.bots.registry import get_bot
    from sqlalchemy import text
    b = get_bot("ebb_pm")
    assert b["display"] == "Ebb PM"
    assert b["strategy"] == "bull_put_spread"
    assert b["ticker"] == "SPY"
    assert b["front_dte"] == 0
    assert b["back_dte"] == 0
    assert b["one_entry_per_day"] is True
    assert b["settle_at_expiry"] is True
    assert b["params"]["short_otm_abs"] == 1.0
    assert b["params"]["spread_abs"] == 2.0
    assert b["params"]["min_credit"] == 0.10
    # Health bands MEASURED 2026-08-15 off this tranche's own gated stream
    # (n=659) at p05/p01, correcting an earlier same-day guess that scaled the
    # old $5-wing bands by a hand-picked factor instead of measuring.
    bands = b["health_bands"]
    assert bands["watch_roll60"] == -87.0
    assert bands["demote_roll60"] == -196.0
    assert bands["demote_roll120"] == 0.0
    assert bands["min_credit20"] == 15.0
    # VIX decay gate OFF since 2026-09-02 (0 = explicit off; None would be
    # re-backfilled). On this cell the gate cost $509/yr and did not cut
    # drawdown; SPARK/ebb keeps it. See the registry comment.
    assert b["defaults"]["vix_decay_max"] == 0
    d = b["defaults"]
    assert d["starting_capital"] == 3000.0
    assert d["enabled"] is False        # no bot ships armed
    assert d["max_contracts"] == 1
    assert d["max_concurrent_positions"] == 1
    assert d["entry_start_ct"] == "13:05"
    assert d["entry_end_ct"] == "13:10"
    assert d["discord_alerts"] is True
    assert b["discord_webhook_env"] == "RISK_ADVISOR_DISCORD_WEBHOOK"

    eng = db_session.get_bind()
    row = eng.connect().execute(text("SELECT enabled FROM ebb_pm_config WHERE id=1")).mappings().first()
    assert row is not None
    assert bool(row["enabled"]) is False
