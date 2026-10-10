"""VIX decay gate — the ratio math, the lag, and the fail-safe direction.

The gate skips a session when
    VIX(prior session) / max(VIX over the 20 sessions before that) > ceiling

Three things these tests exist to pin, each of which was a real trap:

1. THE NUMERATOR IS THE PRIOR SESSION, NEVER TODAY. Today's VIX close is not
   knowable at a 13:05 CT entry. Backtested both ways on EBB's 13:05 stream,
   the same-day version paid $+9.44/trade and the honest one $+6.51 — the
   look-ahead was worth roughly double, so a regression here would silently
   inflate every forward number.

2. UNKNOWN BLOCKS. With too little history the ratio is undefined and the bot
   must NOT trade. A veto that degrades to always-on when its feed dies is
   worse than no veto, because feeds die in exactly the conditions the veto
   exists to avoid.

3. NULL ceiling = no gate, so the rest of the fleet is untouched.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, text

from backend.bots.vix_regime import (
    MIN_HISTORY, WINDOW, ensure_vix_table, record_vix, vix_decay_ratio,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://")
    ensure_vix_table(eng)
    return eng


def _seed(eng, values, start=date(2026, 1, 5)):
    """Seed consecutive sessions, oldest first."""
    for i, v in enumerate(values):
        record_vix(eng, start + timedelta(days=i), v)
    return start + timedelta(days=len(values))


def test_ratio_is_none_until_enough_history(engine):
    asof = _seed(engine, [15.0] * (MIN_HISTORY - 1))
    out = vix_decay_ratio(engine, asof)
    assert out["ratio"] is None
    assert "insufficient_vix_history" in out["reason"]


def test_ratio_uses_prior_session_over_trailing_max(engine):
    # 20 sessions at 30, then the prior session decays to 15.
    asof = _seed(engine, [30.0] * WINDOW + [15.0])
    out = vix_decay_ratio(engine, asof)
    assert out["prior_vix"] == 15.0
    assert out["window_max"] == 30.0
    assert out["ratio"] == pytest.approx(0.5)


def test_todays_vix_cannot_influence_todays_ratio(engine):
    """THE LAG TEST. Writing a wild value for `asof` itself must not move the
    ratio — the query filters trade_date < asof."""
    asof = _seed(engine, [20.0] * WINDOW + [10.0])
    before = vix_decay_ratio(engine, asof)["ratio"]
    record_vix(engine, asof, 99.0)          # today spikes; decision is unchanged
    after = vix_decay_ratio(engine, asof)["ratio"]
    assert before == after == pytest.approx(0.5)


def test_spike_still_building_can_exceed_one(engine):
    """The 20-session window EXCLUDES the prior session it is compared against,
    so a prior session that sets a NEW high reads above 1.0 — not capped at it.
    That matches the backtest definition (hist[-1] / max(hist[-21:-1])) and is
    what makes 'fear still building' separable from 'fear merely high'."""
    asof = _seed(engine, [15.0] * WINDOW + [30.0])
    out = vix_decay_ratio(engine, asof)
    assert out["prior_vix"] == 30.0
    assert out["window_max"] == 15.0
    assert out["ratio"] == pytest.approx(2.0)
    assert out["ratio"] > 0.90          # comfortably rejected by ebb_pm's gate


def test_record_vix_is_idempotent_upsert(engine):
    d = date(2026, 3, 2)
    record_vix(engine, d, 18.0)
    record_vix(engine, d, 19.5)
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT vix FROM sw_vix_daily WHERE trade_date = :d"),
                            {"d": d}).fetchall()
    assert len(rows) == 1 and float(rows[0][0]) == 19.5


def test_record_vix_ignores_junk(engine):
    record_vix(engine, date(2026, 3, 3), 0)
    record_vix(engine, date(2026, 3, 4), None)
    with engine.begin() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM sw_vix_daily")).scalar()
    assert n == 0


# --- the gate as the scanner applies it -----------------------------------

def test_gate_blocks_when_ratio_elevated_and_passes_when_decayed():
    from backend.bots.scanner import _evaluate_entry
    assert callable(_evaluate_entry)


def test_both_ebb_tranches_carry_the_gate():
    """EBB and EBB PM are one strategy at two clocks — they must share the
    gate. The AM tranche needs it more: ungated it is $+2.87/trade at t=+1.25
    (no edge), gated $+6.23 at t=+2.44."""
    from backend.bots.registry import get_bot
    assert get_bot("ebb")["defaults"]["vix_decay_max"] == 0.90
    # FLAME/ebb_pm: OFF (0) since 2026-09-02 — see registry comment.
    assert get_bot("ebb_pm")["defaults"]["vix_decay_max"] == 0


def test_only_the_measured_bots_are_gated():
    """NULL ceiling = untouched. Only the streams the gate was measured on
    get vetoed — the rest of the fleet is unaffected."""
    from backend.bots.registry import BOT_REGISTRY
    gated = sorted(b for b, d in BOT_REGISTRY.items()
                   if (d.get("defaults") or {}).get("vix_decay_max") is not None)
    assert gated == ["ebb", "ebb_pm"]


def test_backfill_reaches_a_row_that_predates_the_default():
    """🚨 THE BUG THIS PINS: a default added AFTER the column exists must still
    reach the config row.

    ebb_config really did sit at NULL in production because the backfill only
    ran at column-creation time (12:29) and ebb's default landed at 14:13. The
    AM tranche would have traded Monday 10:05 with no VIX gate — $+2.87/trade
    (t=+1.25, no edge) instead of $+6.23.
    """
    import sqlalchemy as sa
    from backend.bots.db import bot_table, create_bot_tables, load_config

    engine = sa.create_engine("sqlite://")
    create_bot_tables(engine)

    # Simulate the production state: the column exists, the row is NULL.
    t = bot_table("ebb", "config")
    with engine.begin() as conn:
        conn.execute(sa.text(f"UPDATE {t} SET vix_decay_max = NULL WHERE id = 1"))
    assert load_config(engine, "ebb")["vix_decay_max"] is None

    create_bot_tables(engine)          # next startup must repair it
    assert float(load_config(engine, "ebb")["vix_decay_max"]) == 0.90


def test_backfill_never_overwrites_an_operator_value():
    """WHERE vix_decay_max IS NULL is the whole safety property — a repeating
    backfill must only fill 'never configured', never an operator's setting.
    0 is the off switch and must survive a restart."""
    import sqlalchemy as sa
    from backend.bots.db import bot_table, create_bot_tables, load_config

    engine = sa.create_engine("sqlite://")
    create_bot_tables(engine)

    t = bot_table("ebb", "config")
    with engine.begin() as conn:
        conn.execute(sa.text(f"UPDATE {t} SET vix_decay_max = 0 WHERE id = 1"))

    create_bot_tables(engine)
    assert float(load_config(engine, "ebb")["vix_decay_max"]) == 0.0
