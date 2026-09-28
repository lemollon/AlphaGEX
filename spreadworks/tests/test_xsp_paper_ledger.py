"""EMBER XSP Flow paper ledger -- table create, unarmed logging, no-order
guarantee, settlement calc, and idempotency.

WHY THIS TABLE EXISTS: XSP Flow is paused live (EMBER_XSP_LIVE=0) but Leron
wants its UP/calls signal paper-tracked going forward. See
backend/ember/xsp_paper_ledger.py's module docstring for the full design.

🚨 THE ONE THING THIS FILE MUST PROVE: nothing here ever checks
EMBER_XSP_LIVE, never places an order, and never takes the fleet's shared
advisory lock -- see test_logging_ignores_live_flag_entirely,
test_no_order_tools_or_broker_lock_anywhere_in_the_module, and
test_public_functions_take_no_live_or_armed_parameter below.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text

from backend.ember import xsp_flow_live as live
from backend.ember import xsp_paper_ledger as ledger

TABLE = ledger.TABLE
CT = ZoneInfo("America/Chicago")


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    ledger.ensure_table(eng)
    return eng


def _all_rows(engine):
    with engine.begin() as conn:
        return conn.execute(text(f"SELECT * FROM {TABLE}")).mappings().all()


def _history_row(d: date, direction: str | None, fired_spot: float = 687.40,
                  fired_at: datetime | None = None, close_spot: float | None = None,
                  armed: bool = True, putcall_z: float = 2.1) -> dict:
    return {
        "d": d.isoformat(),
        "armed": armed,
        "putcall_z": putcall_z,
        "fired_dir": direction,
        "fired_at": (fired_at or datetime(2026, 9, 21, 15, 2, tzinfo=timezone.utc)).isoformat(),
        "ref_spot": 685.0,
        "fired_spot": fired_spot,
        "close_spot": close_spot,
        "outcome_pct": None,
    }


def _fresh_up_history(d: date, now_ct: datetime) -> list[dict]:
    fired_at = now_ct.astimezone(timezone.utc)
    return [_history_row(d, "UP", fired_spot=687.40, fired_at=fired_at)]


def _fake_chain_ok(expiry: str) -> list[dict]:
    return [
        {"strike": 689.0, "option_type": "call", "bid": 1.10, "ask": 1.20},
        {"strike": 690.0, "option_type": "call", "bid": 1.02, "ask": 1.12},
    ]


def _fake_chain_wide_debit(expiry: str) -> list[dict]:
    return [
        {"strike": 689.0, "option_type": "call", "bid": 0.50, "ask": 3.00},
        {"strike": 690.0, "option_type": "call", "bid": 0.10, "ask": 0.20},
    ]


def _fake_chain_missing_short(expiry: str) -> list[dict]:
    return [{"strike": 689.0, "option_type": "call", "bid": 1.10, "ask": 1.20}]


# ---------------------------------------------------------------- table create

def test_ensure_table_is_idempotent(engine):
    ledger.ensure_table(engine)
    ledger.ensure_table(engine)
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"
        ), {"t": TABLE}).scalar_one()
    assert n == 1


# ---------------------------------------------------------------- unarmed logging

def test_logging_ignores_live_flag_entirely(engine, monkeypatch):
    """🚨 THE REQUIREMENT: paper logging must not depend on EMBER_XSP_LIVE.
    Setting it to 0, 1, or leaving it unset must not change what gets
    written for the identical signal/quote inputs."""
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = _fresh_up_history(d, now_ct)

    for live_flag in ("0", "1"):
        eng = create_engine("sqlite:///:memory:", future=True)
        monkeypatch.setenv("EMBER_XSP_LIVE", live_flag)
        ok = ledger.record_tick(
            eng, now_ct, history_fn=lambda: history, chain_fn=_fake_chain_ok
        )
        assert ok is True
        rows = _all_rows(eng)
        assert len(rows) == 1
        assert rows[0]["would_trade"] in (1, True)
        assert rows[0]["debit"] == pytest.approx(0.18)


def test_public_functions_take_no_live_or_armed_parameter():
    """Guards against a future edit quietly re-introducing an arming gate."""
    for fn in (ledger.record_tick, ledger.settle_pending, ledger.ensure_table, ledger.export_csv):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"live", "armed", "dry_run", "cfg"}), fn.__name__


# ---------------------------------------------------------------- no-order / no-lock guarantee

def test_no_order_tools_or_broker_lock_anywhere_in_the_module():
    """Structural proof: this module never references the live executor's
    order tools or the fleet's advisory-lock machinery."""
    source = inspect.getsource(ledger)
    for banned in ("ORDER_TOOLS", "place_option_order", "cancel_option_order",
                   "_acquire_cycle_lock", "pg_try_advisory_lock", "run_agent"):
        assert banned not in source, banned


def test_record_tick_never_calls_the_broker_chain_fn_for_a_quiet_day(engine):
    """No signal today -> zero calls to chain_fn (there is nothing to price)."""
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = [_history_row(d, None)]
    calls = []

    def _tracking_chain(expiry):
        calls.append(expiry)
        return _fake_chain_ok(expiry)

    ledger.record_tick(engine, now_ct, history_fn=lambda: history, chain_fn=_tracking_chain)
    assert calls == []
    rows = _all_rows(engine)
    assert len(rows) == 1
    assert rows[0]["would_trade"] in (0, False)
    assert rows[0]["reason"] == "no frozen signal today"


# ---------------------------------------------------------------- decision + NBBO capture

def test_fresh_signal_captures_entry_nbbo_and_debit(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = _fresh_up_history(d, now_ct)

    ok = ledger.record_tick(engine, now_ct, history_fn=lambda: history, chain_fn=_fake_chain_ok)
    assert ok is True
    rows = _all_rows(engine)
    assert len(rows) == 1
    row = rows[0]
    assert row["direction"] == "UP"
    assert row["option_type"] == "C"
    assert row["long_strike"] == 689
    assert row["short_strike"] == 690
    assert row["long_ask"] == pytest.approx(1.20)
    assert row["short_bid"] == pytest.approx(1.02)
    assert row["debit"] == pytest.approx(0.18)
    assert row["would_trade"] in (1, True)
    assert row["captured_at"] is not None


def test_debit_outside_cap_records_would_trade_false(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = _fresh_up_history(d, now_ct)

    ledger.record_tick(engine, now_ct, history_fn=lambda: history, chain_fn=_fake_chain_wide_debit)
    row = _all_rows(engine)[0]
    assert row["would_trade"] in (0, False)
    assert "outside" in row["reason"]
    assert row["debit"] == pytest.approx(2.90)


def test_missing_leg_quote_records_a_reason_without_a_debit(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = _fresh_up_history(d, now_ct)

    ledger.record_tick(engine, now_ct, history_fn=lambda: history, chain_fn=_fake_chain_missing_short)
    row = _all_rows(engine)[0]
    assert row["would_trade"] in (0, False)
    assert "missing contract" in row["reason"]
    assert row["debit"] is None


def test_stale_signal_past_cutoff_is_a_terminal_miss(engine):
    d = date(2026, 9, 21)
    fired_at = datetime(2026, 9, 21, 14, 30, tzinfo=timezone.utc)  # 9:30 CT
    now_ct = datetime(2026, 9, 21, 14, 58, tzinfo=CT)  # after the 14:54 cutoff
    history = [_history_row(d, "UP", fired_spot=687.40, fired_at=fired_at)]

    calls = []
    ledger.record_tick(engine, now_ct, history_fn=lambda: history,
                        chain_fn=lambda e: (calls.append(e), _fake_chain_ok(e))[1])
    row = _all_rows(engine)[0]
    assert row["would_trade"] in (0, False)
    assert "cutoff" in row["reason"]
    assert calls == []  # cutoff is checked before any chain lookup


# ---------------------------------------------------------------- idempotency

def test_second_tick_same_day_is_a_noop_after_capture(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    history = _fresh_up_history(d, now_ct)
    calls = []

    def _tracking_chain(expiry):
        calls.append(expiry)
        return _fake_chain_ok(expiry)

    ledger.record_tick(engine, now_ct, history_fn=lambda: history, chain_fn=_tracking_chain)
    assert len(calls) == 1
    first_row = _all_rows(engine)[0]

    later_ct = now_ct.replace(minute=3)
    ledger.record_tick(engine, later_ct, history_fn=lambda: history, chain_fn=_tracking_chain)
    assert len(calls) == 1  # no second Tradier call
    rows = _all_rows(engine)
    assert len(rows) == 1  # still one row for the day, not two
    assert rows[0]["debit"] == first_row["debit"]


def test_a_new_trade_date_is_a_new_row(engine):
    d1, d2 = date(2026, 9, 21), date(2026, 9, 22)
    now1 = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    now2 = datetime(2026, 9, 22, 10, 2, tzinfo=CT)

    ledger.record_tick(engine, now1, history_fn=lambda: _fresh_up_history(d1, now1), chain_fn=_fake_chain_ok)
    ledger.record_tick(engine, now2, history_fn=lambda: _fresh_up_history(d2, now2), chain_fn=_fake_chain_ok)
    rows = _all_rows(engine)
    assert len(rows) == 2
    assert {str(r["trade_date"]) for r in rows} == {"2026-09-21", "2026-09-22"}


def test_outside_scheduled_window_is_a_noop(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 7, 0, tzinfo=CT)  # before 8:30 CT
    ok = ledger.record_tick(engine, now_ct, history_fn=lambda: _fresh_up_history(d, now_ct),
                             chain_fn=_fake_chain_ok)
    assert ok is False
    assert _all_rows(engine) == []


# ---------------------------------------------------------------- settlement

def test_settle_pending_computes_payout_and_pnl_from_close_spot(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    ledger.record_tick(engine, now_ct, history_fn=lambda: _fresh_up_history(d, now_ct),
                        chain_fn=_fake_chain_ok)
    row = _all_rows(engine)[0]
    assert row["debit"] == pytest.approx(0.18)

    settled_history = [_history_row(d, "UP", fired_spot=687.40, close_spot=690.50)]
    n = ledger.settle_pending(engine, history_fn=lambda: settled_history)
    assert n == 1

    settled = _all_rows(engine)[0]
    expected_payout = live.settlement_payout("UP", 690.50, 689, 690)
    assert settled["payout"] == pytest.approx(expected_payout)
    assert settled["settlement_value"] == pytest.approx(690.50)
    assert settled["pnl"] == pytest.approx(round(expected_payout - 0.18 * 100.0, 2))
    assert settled["settled_at"] is not None


def test_settle_pending_leaves_rows_pending_without_a_close_spot(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    ledger.record_tick(engine, now_ct, history_fn=lambda: _fresh_up_history(d, now_ct),
                        chain_fn=_fake_chain_ok)

    n = ledger.settle_pending(engine, history_fn=lambda: [_history_row(d, "UP", close_spot=None)])
    assert n == 0
    row = _all_rows(engine)[0]
    assert row["settled_at"] is None


def test_settle_pending_skips_rows_that_would_not_have_traded(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    ledger.record_tick(engine, now_ct, history_fn=lambda: _fresh_up_history(d, now_ct),
                        chain_fn=_fake_chain_wide_debit)
    row = _all_rows(engine)[0]
    assert row["would_trade"] in (0, False)

    n = ledger.settle_pending(engine, history_fn=lambda: [_history_row(d, "UP", close_spot=690.50)])
    assert n == 0  # never priced as a trade, nothing to settle


def test_settle_pending_is_idempotent(engine):
    d = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 10, 2, tzinfo=CT)
    ledger.record_tick(engine, now_ct, history_fn=lambda: _fresh_up_history(d, now_ct),
                        chain_fn=_fake_chain_ok)
    settled_history = [_history_row(d, "UP", fired_spot=687.40, close_spot=690.50)]

    n1 = ledger.settle_pending(engine, history_fn=lambda: settled_history)
    n2 = ledger.settle_pending(engine, history_fn=lambda: settled_history)
    assert n1 == 1
    assert n2 == 0  # already settled -- no re-write
    assert len(_all_rows(engine)) == 1


# ---------------------------------------------------------------- registration gating

def test_register_is_a_noop_when_xsp_is_disabled(monkeypatch):
    monkeypatch.delenv("EMBER_XSP_ENABLED", raising=False)

    class _FakeScheduler:
        def add_job(self, *a, **k):
            raise AssertionError("add_job should never be called when EMBER_XSP_ENABLED is unset")

    ledger.register(_FakeScheduler())  # must not raise, must not call add_job


def test_register_does_not_read_the_live_flag(monkeypatch):
    """register() gates only on EMBER_XSP_ENABLED -- EMBER_XSP_LIVE must have
    zero effect on whether the paper jobs get scheduled."""
    monkeypatch.setenv("EMBER_XSP_ENABLED", "1")
    monkeypatch.setenv("EMBER_XSP_LIVE", "0")
    jobs = []

    class _FakeScheduler:
        def add_job(self, fn, *a, **k):
            jobs.append(k.get("id"))

    ledger.register(_FakeScheduler())
    assert set(jobs) == {"ember_xsp_paper_eval", "ember_xsp_paper_settle"}
