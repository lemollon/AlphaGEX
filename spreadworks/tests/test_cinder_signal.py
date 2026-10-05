"""Pure-function tests for CINDER's trigger, cooldown, and term-structure
logic -- mirrors test_squeeze_reactive_alerts.py's own conventions (no
network, no MCP). The DB-touching legs (gex_leg, vix_ratio_leg's
live_vix_ratio call, fetch_vol_reading) are exercised through a real SQLite
engine the same way squeeze_reactive's test drives `run_reactive_scan`
through a SQLite engine with HTTP mocked out -- here there is no HTTP at
all to mock, so the DB is the only fixture needed.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine, text

from backend import cinder_signal as cinder

TODAY = date(2026, 10, 2)


# ---------------------------------------------------------------------------
# Cooldown logic -- pure
# ---------------------------------------------------------------------------

def test_cooldown_ok_with_no_prior_entry():
    assert cinder.cooldown_ok(None, TODAY) is True


def test_cooldown_blocks_within_window():
    last = TODAY - timedelta(days=3)
    assert cinder.cooldown_ok(last, TODAY) is False


def test_cooldown_clears_at_exactly_the_boundary():
    last = TODAY - timedelta(days=cinder.COOLDOWN_DAYS)
    assert cinder.cooldown_ok(last, TODAY) is True


def test_cooldown_blocks_one_day_short_of_the_boundary():
    last = TODAY - timedelta(days=cinder.COOLDOWN_DAYS - 1)
    assert cinder.cooldown_ok(last, TODAY) is False


def test_last_entry_date_reads_the_newest_row():
    engine = create_engine("sqlite://")
    cinder.ensure_cinder_tables(engine)
    assert cinder.last_entry_date(engine) is None
    cinder.open_position(engine, TODAY - timedelta(days=10),
                         datetime(2026, 9, 22, 11, 30), 670.0, 670.0, 680.0,
                         TODAY - timedelta(days=9), 3.50)
    cinder.close_position(engine, TODAY - timedelta(days=10),
                          datetime(2026, 9, 23, 15, 55), 7.00, "target_2x", 1.0)
    cinder.open_position(engine, TODAY - timedelta(days=2),
                         datetime(2026, 9, 30, 11, 30), 672.0, 672.0, 682.0,
                         TODAY - timedelta(days=1), 3.20)
    assert cinder.last_entry_date(engine) == TODAY - timedelta(days=2)


# ---------------------------------------------------------------------------
# Term-structure leg -- pure, including the "missing data = blocked, not a
# silent pass" case this task explicitly calls out.
# ---------------------------------------------------------------------------

NOW_UTC = datetime(2026, 10, 2, 15, 32)  # 11:32 ET-ish, naive UTC for the test


def _reading(price: float, minutes_old: int = 2, fresh: bool = True) -> dict:
    return {"symbol": "X", "price": price,
            "captured_at": NOW_UTC - timedelta(minutes=minutes_old), "fresh": fresh}


def test_term_structure_passes_on_normal_contango():
    vix = _reading(18.0)
    vix3m = _reading(20.0)
    out = cinder.term_structure_leg(vix, vix3m, NOW_UTC)
    assert out["pass"] is True
    assert out["term"] == -2.0
    assert out["reason"] is None


def test_term_structure_fails_on_backwardation():
    vix = _reading(28.0)
    vix3m = _reading(24.0)
    out = cinder.term_structure_leg(vix, vix3m, NOW_UTC)
    assert out["pass"] is False
    assert out["term"] == 4.0


def test_term_structure_blocks_when_vix3m_missing():
    vix = _reading(18.0)
    out = cinder.term_structure_leg(vix, None, NOW_UTC)
    assert out["pass"] is None          # UNKNOWN, never a silent pass
    assert "VIX3M" in out["reason"]


def test_term_structure_blocks_when_vix_missing():
    vix3m = _reading(20.0)
    out = cinder.term_structure_leg(None, vix3m, NOW_UTC)
    assert out["pass"] is None
    assert "VIX" in out["reason"]


def test_term_structure_blocks_when_a_reading_is_stale():
    vix = _reading(18.0, minutes_old=cinder.VOL_READING_STALE_MINUTES + 5)
    vix3m = _reading(20.0)
    out = cinder.term_structure_leg(vix, vix3m, NOW_UTC)
    assert out["pass"] is None
    assert "VIX" in out["reason"]


def test_term_structure_blocks_when_a_reading_was_never_fresh_at_capture():
    vix = _reading(18.0, fresh=False)
    vix3m = _reading(20.0)
    out = cinder.term_structure_leg(vix, vix3m, NOW_UTC)
    assert out["pass"] is None


# ---------------------------------------------------------------------------
# VIX-ratio leg -- the comparison itself is pure; live_vix_ratio's own DB
# read is exercised against a real SQLite engine.
# ---------------------------------------------------------------------------

def test_vix_ratio_leg_blocks_on_missing_reading():
    out = cinder.vix_ratio_leg(None, NOW_UTC)
    assert out["pass"] is None
    assert "missing" in out["reason"]


def test_vix_ratio_leg_blocks_on_stale_reading():
    vix = _reading(18.0, minutes_old=999)
    out = cinder.vix_ratio_leg(vix, NOW_UTC)
    assert out["pass"] is None


def test_vix_ratio_leg_passes_below_trigger(monkeypatch):
    from backend import routes_squeeze as rs
    vix = _reading(15.0)
    monkeypatch.setattr(rs, "live_vix_ratio", lambda vix_now: 0.80)
    out = cinder.vix_ratio_leg(vix, NOW_UTC)
    assert out["pass"] is True
    assert out["ratio"] == 0.80


def test_vix_ratio_leg_fails_at_or_above_trigger(monkeypatch):
    from backend import routes_squeeze as rs
    vix = _reading(22.0)
    monkeypatch.setattr(rs, "live_vix_ratio", lambda vix_now: 0.95)
    out = cinder.vix_ratio_leg(vix, NOW_UTC)
    assert out["pass"] is False


def test_vix_ratio_leg_blocks_on_insufficient_history(monkeypatch):
    from backend import routes_squeeze as rs
    vix = _reading(22.0)
    monkeypatch.setattr(rs, "live_vix_ratio", lambda vix_now: None)
    out = cinder.vix_ratio_leg(vix, NOW_UTC)
    assert out["pass"] is None


# ---------------------------------------------------------------------------
# Combined trigger -- unknown beats failed beats passed; all three must
# agree for `triggered` to be True.
# ---------------------------------------------------------------------------

def test_evaluate_entry_trigger_blocks_when_gex_leg_is_unknown(monkeypatch):
    engine = create_engine("sqlite://")
    cinder.ensure_cinder_tables(engine)
    from backend.bots.gamma_regime import ensure_gamma_table
    ensure_gamma_table(engine)
    # No sw_gamma_daily rows and no sw_live_vol_indices table at all -> every
    # leg unknown.
    out = cinder.evaluate_entry_trigger(engine, TODAY, NOW_UTC)
    assert out["triggered"] is None


def test_evaluate_entry_trigger_fires_when_every_leg_passes(monkeypatch):
    engine = create_engine("sqlite://")
    cinder.ensure_cinder_tables(engine)
    from backend.bots.gamma_regime import ensure_gamma_table, record_gamma
    ensure_gamma_table(engine)
    record_gamma(engine, TODAY - timedelta(days=1), -15e9, spot=670.0, n_contracts=500)

    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS sw_live_vol_indices ("
            " symbol TEXT NOT NULL, captured_at TIMESTAMP NOT NULL,"
            " price DOUBLE PRECISION, source TEXT NOT NULL,"
            " source_timestamp TIMESTAMP, age_seconds DOUBLE PRECISION,"
            " fresh BOOLEAN NOT NULL, reason TEXT,"
            " PRIMARY KEY(symbol, captured_at))"))
        conn.execute(text(
            "INSERT INTO sw_live_vol_indices "
            "(symbol, captured_at, price, source, fresh) "
            "VALUES ('VIX', :ca, 15.0, 'test', 1)"), {"ca": NOW_UTC - timedelta(minutes=1)})
        conn.execute(text(
            "INSERT INTO sw_live_vol_indices "
            "(symbol, captured_at, price, source, fresh) "
            "VALUES ('VIX3M', :ca, 18.0, 'test', 1)"), {"ca": NOW_UTC - timedelta(minutes=1)})

    from backend import routes_squeeze as rs
    monkeypatch.setattr(rs, "live_vix_ratio", lambda vix_now: 0.70)

    out = cinder.evaluate_entry_trigger(engine, TODAY, NOW_UTC)
    assert out["gex"]["pass"] is True
    assert out["term_structure"]["pass"] is True
    assert out["vix_ratio"]["pass"] is True
    assert out["triggered"] is True


# ---------------------------------------------------------------------------
# Entry strike selection -- pure, operates on a get_chain()-shaped dict.
# ---------------------------------------------------------------------------

def _fake_chain(spot=674.30, strikes=None, expiration="2026-10-03"):
    strikes = strikes or [664, 670, 674, 675, 684, 690]
    options = []
    for s in strikes:
        options.append({"strike": s, "type": "call", "bid": s * 0.01, "ask": s * 0.012})
        options.append({"strike": s, "type": "put", "bid": s * 0.01, "ask": s * 0.012})
    return {"spot": spot, "options": options, "expiration": expiration}


def test_select_entry_strikes_happy_path():
    chain = _fake_chain()
    out = cinder.select_entry_strikes(chain)
    assert out["reason"] is None
    assert out["long_strike"] == 674
    assert out["short_strike"] == 684
    assert out["entry_debit"] is not None and out["entry_debit"] > 0


def test_select_entry_strikes_no_width_match():
    chain = _fake_chain(strikes=[670, 674])   # nothing 10 higher than ATM
    out = cinder.select_entry_strikes(chain)
    assert out["reason"] is not None
    assert out["entry_debit"] is None


def test_select_entry_strikes_no_chain():
    out = cinder.select_entry_strikes(None)
    assert out["reason"] == "no live chain available"


# ---------------------------------------------------------------------------
# Exit spread value -- pure.
# ---------------------------------------------------------------------------

def test_spread_value_from_chain_happy_path():
    chain = _fake_chain(expiration="2026-10-03")
    out = cinder.spread_value_from_chain(chain, 674, 684,
                                         expected_expiration=date(2026, 10, 3))
    assert out["reason"] is None
    assert out["value"] == out["long_bid"] - out["short_ask"]


def test_spread_value_from_chain_expiration_mismatch_blocks():
    chain = _fake_chain(expiration="2026-10-10")   # drifted expiry
    out = cinder.spread_value_from_chain(chain, 674, 684,
                                         expected_expiration=date(2026, 10, 3))
    assert out["value"] is None
    assert "does not match" in out["reason"]


# ---------------------------------------------------------------------------
# Full scan, outside the regular session -- cheap no-op, same convention
# squeeze_reactive's own test checks.
# ---------------------------------------------------------------------------

def test_outside_regular_session_is_a_cheap_noop():
    from zoneinfo import ZoneInfo
    engine = create_engine("sqlite://")
    before_hours = datetime(2026, 10, 2, 7, 0, tzinfo=ZoneInfo("America/New_York"))
    summary = cinder.run_cinder_scan(engine, before_hours)
    assert summary["reason"] == "outside the 09:30:00-16:00:00 ET regular session"
    assert summary["entries_opened"] == [] and summary["exits_closed"] == []
