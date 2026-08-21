"""Behavioural tests for the FLOW phantom-trade restatement.

This rewrites BOOKED HISTORY, so the tests exercise what actually matters: that
it corrects exactly the three known rows, that running it twice does not
double-apply, that it refuses to touch a row whose value has drifted from what
the analysis was performed against, and that every original is recoverable.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from backend.flow_restatement import (
    AUDIT, RESTATEMENTS, TABLE, apply_flow_restatements,
)

_CLOSED_DDL = f"""
CREATE TABLE {TABLE} (
    position_id     TEXT PRIMARY KEY,
    close_price     NUMERIC(10,4) NOT NULL,
    close_time      TIMESTAMP NOT NULL,
    close_reason    TEXT NOT NULL,
    realized_pnl    NUMERIC(10,2) NOT NULL,
    contracts       INTEGER NOT NULL,
    legs            TEXT NOT NULL,
    entry_price     NUMERIC(10,4) NOT NULL,
    entry_time      TIMESTAMP NOT NULL,
    ticker          TEXT NOT NULL,
    strategy        TEXT NOT NULL
)
"""

# The three phantoms as the ledger actually holds them, plus one ordinary
# trade that must be left completely alone.
SEED = [
    ("flow-2026-08-18-d2e4ed9e", 0.84, 5319.00, 27, 2.81, "2026-08-18 13:30:00"),
    ("flow-2026-08-12-58075fae", 0.875, 791.00, 14, 1.44, "2026-08-12 13:30:00"),
    ("flow-2026-08-21-7a00471b", 0.80, 1988.00, 28, 1.51, "2026-08-21 13:30:00"),
    ("flow-2026-08-20-19f32bb8", 0.02, 1470.00, 21, 0.72, "2026-08-20 13:51:00"),
]


def _engine(seed=SEED):
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text(_CLOSED_DDL))
        for pid, cp, pnl, n, ep, et in seed:
            c.execute(text(
                f"INSERT INTO {TABLE} VALUES (:p, :cp, :ct, 'PT', :pnl, :n, "
                "'[]', :ep, :et, 'SPY', 'iron_condor')"),
                {"p": pid, "cp": cp, "ct": et, "pnl": pnl, "n": n,
                 "ep": ep, "et": et})
    return eng


def _pnl(eng, pid):
    with eng.begin() as c:
        return float(c.execute(
            text(f"SELECT realized_pnl FROM {TABLE} WHERE position_id = :p"),
            {"p": pid}).scalar())


def _entry(eng, pid):
    with eng.begin() as c:
        return float(c.execute(
            text(f"SELECT entry_price FROM {TABLE} WHERE position_id = :p"),
            {"p": pid}).scalar())


def test_applies_all_three():
    eng = _engine()
    out = apply_flow_restatements(eng)
    assert out["applied"] == 3
    assert out["skipped"] == [] and out["missing"] == []
    assert _pnl(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(-369.90)
    assert _pnl(eng, "flow-2026-08-12-58075fae") == pytest.approx(-273.00)
    assert _pnl(eng, "flow-2026-08-21-7a00471b") == pytest.approx(196.00)


def test_total_adjustment_is_the_number_we_quoted():
    out = apply_flow_restatements(_engine())
    assert out["total_adjustment"] == pytest.approx(-8544.90, abs=0.01)


def test_entry_prices_corrected_too():
    eng = _engine()
    apply_flow_restatements(eng)
    assert _entry(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(0.703)
    assert _entry(eng, "flow-2026-08-12-58075fae") == pytest.approx(0.680)
    assert _entry(eng, "flow-2026-08-21-7a00471b") == pytest.approx(0.870)


def test_every_corrected_credit_is_inside_the_clean_band():
    """The reconstruction's own evidence: corrected credits must look like
    ordinary FLOW fills (10.4-17.7% of the $5 wing), not like the 28-56%
    phantoms. If a future edit pushes one outside, that edit is wrong."""
    for r in RESTATEMENTS:
        frac = r["new_entry_price"] / 5.0
        assert 0.10 <= frac <= 0.18, f"{r['position_id']} at {frac:.1%}"


def test_leaves_the_ordinary_trade_untouched():
    eng = _engine()
    apply_flow_restatements(eng)
    assert _pnl(eng, "flow-2026-08-20-19f32bb8") == pytest.approx(1470.00)
    assert _entry(eng, "flow-2026-08-20-19f32bb8") == pytest.approx(0.72)


def test_second_run_is_a_no_op():
    eng = _engine()
    apply_flow_restatements(eng)
    out = apply_flow_restatements(eng)
    assert out["applied"] == 0 and out["already"] == 3
    assert out["total_adjustment"] == 0.0
    assert _pnl(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(-369.90)


def test_ten_runs_do_not_compound():
    eng = _engine()
    for _ in range(10):
        apply_flow_restatements(eng)
    assert _pnl(eng, "flow-2026-08-21-7a00471b") == pytest.approx(196.00)
    with eng.begin() as c:
        assert c.execute(text(f"SELECT COUNT(*) FROM {AUDIT}")).scalar() == 3


def test_refuses_a_row_that_has_drifted():
    """If the ledger no longer holds the value this analysis was performed
    against, the row is SKIPPED — never overwritten with a number derived from
    a state that no longer exists."""
    seed = list(SEED)
    seed[0] = ("flow-2026-08-18-d2e4ed9e", 0.84, 4000.00, 27, 2.81,
               "2026-08-18 13:30:00")
    eng = _engine(seed)
    out = apply_flow_restatements(eng)
    assert out["applied"] == 2
    assert len(out["skipped"]) == 1
    assert "d2e4ed9e" in out["skipped"][0]
    assert _pnl(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(4000.00)


def test_a_skipped_row_is_not_audited_so_it_can_be_retried():
    seed = list(SEED)
    seed[0] = ("flow-2026-08-18-d2e4ed9e", 0.84, 4000.00, 27, 2.81,
               "2026-08-18 13:30:00")
    eng = _engine(seed)
    apply_flow_restatements(eng)
    with eng.begin() as c:
        assert c.execute(text(
            f"SELECT COUNT(*) FROM {AUDIT} WHERE position_id = "
            "'flow-2026-08-18-d2e4ed9e'")).scalar() == 0


def test_missing_position_reported_not_crashed():
    eng = _engine([SEED[0]])
    out = apply_flow_restatements(eng)
    assert out["applied"] == 1
    assert len(out["missing"]) == 2


def test_originals_are_recoverable():
    """The whole point of the audit table: the rollback in the .sql script must
    actually restore the booked values."""
    eng = _engine()
    apply_flow_restatements(eng)
    with eng.begin() as c:
        c.execute(text(
            f"UPDATE {TABLE} SET entry_price = (SELECT orig_entry_price FROM "
            f"{AUDIT} r WHERE r.position_id = {TABLE}.position_id), "
            f"realized_pnl = (SELECT orig_realized_pnl FROM {AUDIT} r WHERE "
            f"r.position_id = {TABLE}.position_id) WHERE position_id IN "
            f"(SELECT position_id FROM {AUDIT})"))
    assert _pnl(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(5319.00)
    assert _pnl(eng, "flow-2026-08-12-58075fae") == pytest.approx(791.00)
    assert _pnl(eng, "flow-2026-08-21-7a00471b") == pytest.approx(1988.00)
    assert _entry(eng, "flow-2026-08-18-d2e4ed9e") == pytest.approx(2.81)


def test_audit_keeps_the_reason_and_the_legs():
    eng = _engine()
    apply_flow_restatements(eng)
    with eng.begin() as c:
        reason, legs = c.execute(text(
            f"SELECT reason, orig_legs FROM {AUDIT} WHERE position_id = "
            "'flow-2026-08-21-7a00471b'")).first()
    assert "opening-bell" in reason
    assert legs == "[]"


def test_no_engine_is_survivable():
    assert apply_flow_restatements(None)["applied"] == 0


def test_missing_table_is_non_fatal():
    """A cold environment with no FLOW ledger must boot, not crash."""
    out = apply_flow_restatements(create_engine("sqlite://"))
    assert out["applied"] == 0
    assert "error" in out
