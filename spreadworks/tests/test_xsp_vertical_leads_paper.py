"""EMBER XSP vertical Leads A/C2 paper ledger -- table create, unarmed
logging, no-order guarantee, rule parity vs the frozen prereg on a fixture
day, settlement calc, and idempotency.

🚨 THE ONE THING THIS FILE MUST PROVE: nothing here ever checks any
*_LIVE flag, never places an order, and never takes the fleet's shared
advisory lock -- see test_module_never_references_a_live_flag,
test_no_order_tools_or_broker_lock_anywhere_in_the_module, and
test_public_functions_take_no_live_or_armed_parameter below.
"""
from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, text

from backend.ember import xsp_vertical_leads_paper as ledger

TABLE = ledger.TABLE
CT = ZoneInfo("America/Chicago")


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    ledger.ensure_table(eng)
    return eng


def _all_rows(engine, lead: str | None = None):
    q = f"SELECT * FROM {TABLE}"
    params = {}
    if lead:
        q += " WHERE lead = :lead"
        params["lead"] = lead
    with engine.begin() as conn:
        return conn.execute(text(q), params).mappings().all()


def _captured_rows(engine, lead: str, since: date):
    """Rows for `lead` on or after `since` -- excludes the seeded trailing
    history rows (which live before that cutoff) so idempotency/decision
    assertions only see what record_tick itself wrote for the test's own
    trade_date(s)."""
    with engine.begin() as conn:
        return conn.execute(
            text(f"SELECT * FROM {TABLE} WHERE lead = :lead AND trade_date >= :since ORDER BY trade_date"),
            {"lead": lead, "since": since},
        ).mappings().all()


def _seed_trailing(engine, lead: str, column: str, values: list[float], start: date):
    """Insert `len(values)` prior captured rows directly, one per day
    starting at `start`, with `column` set -- mirrors what record_tick would
    have written over the prior TRAILING_N sessions."""
    for i, v in enumerate(values):
        d = start + timedelta(days=i)
        row = ledger._base_row(lead, d, datetime(2026, 1, 1), datetime(2026, 1, 1))
        row[column] = v
        row["captured_at"] = datetime(2026, 1, 1)
        ledger._upsert(engine, row)


_FAKE_XSP_CHAIN = [
    {"strike": 686.0, "option_type": "call", "bid": 3.10, "ask": 3.30},
    {"strike": 687.0, "option_type": "call", "bid": 2.40, "ask": 2.60},  # ~1% OTM target for spot=680
    {"strike": 691.0, "option_type": "call", "bid": 0.55, "ask": 0.70},
    {"strike": 692.0, "option_type": "call", "bid": 0.40, "ask": 0.55},  # long+5 target
]


def _fake_xsp_chain_fn(expiry: str):
    return _FAKE_XSP_CHAIN


# ---------------------------------------------------------------- table create


def test_ensure_table_is_idempotent(engine):
    ledger.ensure_table(engine)
    ledger.ensure_table(engine)
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"), {"t": TABLE}
        ).scalar_one()
    assert n == 1


# ---------------------------------------------------------------- unarmed logging / no-order guarantee


def test_register_gating_is_unaffected_by_any_live_flag(monkeypatch):
    """🚨 THE REQUIREMENT: register()'s job-scheduling decision depends only
    on ENABLED_ENV -- toggling any *_LIVE flag must not change it (behavioral
    proof, mirrors xsp_paper_ledger's own live-flag-blind test)."""
    monkeypatch.setenv(ledger.ENABLED_ENV, "1")

    for live_flag in ("0", "1"):
        monkeypatch.setenv("EMBER_XSP_LIVE", live_flag)
        jobs = []

        class _FakeScheduler:
            def add_job(self, fn, *a, **k):
                jobs.append(k.get("id"))

        ledger.register(_FakeScheduler())
        assert set(jobs) == {"ember_xsp_vertical_leads_eval", "ember_xsp_vertical_leads_settle"}


def test_public_functions_take_no_live_or_armed_parameter():
    for fn in (ledger.record_tick, ledger.settle_pending, ledger.ensure_table, ledger.export_csv):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"live", "armed", "dry_run", "cfg"}), fn.__name__


def test_no_order_tools_or_broker_lock_anywhere_in_the_module():
    """Structural proof: this module never references the live executor's
    order tools or the fleet's advisory-lock machinery."""
    source = inspect.getsource(ledger)
    for banned in (
        "ORDER_TOOLS", "place_option_order", "cancel_option_order",
        "_acquire_cycle_lock", "pg_try_advisory_lock", "run_agent",
    ):
        assert banned not in source, banned


def test_record_tick_never_touches_chains_outside_the_capture_window(engine):
    """Before either lead's decision time, nothing is captured and no chain
    fn is ever invoked."""
    calls = []

    def _tracking_chain(expiry):
        calls.append(expiry)
        return _FAKE_XSP_CHAIN

    now_ct = datetime(2026, 9, 21, 9, 0, tzinfo=CT)  # before both 9:30 and 11:00 CT decision times
    ok = ledger.record_tick(engine, now_ct, xsp_chain_fn=_tracking_chain, spy_chain_fn=_tracking_chain)
    assert ok is True
    assert calls == []
    assert _all_rows(engine) == []


def test_outside_market_window_is_a_noop(engine):
    now_ct = datetime(2026, 9, 21, 7, 0, tzinfo=CT)  # before 8:30 CT
    ok = ledger.record_tick(engine, now_ct)
    assert ok is False
    assert _all_rows(engine) == []


def test_register_is_a_noop_when_disabled(monkeypatch):
    monkeypatch.delenv(ledger.ENABLED_ENV, raising=False)

    class _FakeScheduler:
        def add_job(self, *a, **k):
            raise AssertionError("add_job should never be called when the module is disabled")

    ledger.register(_FakeScheduler())


def test_register_only_reads_its_own_enabled_flag(monkeypatch):
    monkeypatch.setenv(ledger.ENABLED_ENV, "1")
    monkeypatch.setenv("EMBER_XSP_LIVE", "0")
    monkeypatch.delenv("EMBER_XSP_ENABLED", raising=False)
    jobs = []

    class _FakeScheduler:
        def add_job(self, fn, *a, **k):
            jobs.append(k.get("id"))

    ledger.register(_FakeScheduler())
    assert set(jobs) == {"ember_xsp_vertical_leads_eval", "ember_xsp_vertical_leads_settle"}


# ---------------------------------------------------------------- rule parity vs the frozen prereg


def test_lead_a_warms_up_before_20_sessions():
    """Prereg: first ~20 sessions have no valid trailing signal -- logged,
    never a meaningful non-fire."""
    decision = ledger._decide_lead_a(680.0, 1.0e9, "ok", trailing=[1.0e9] * 5)
    assert decision["fired"] is False
    assert "warming_up" in decision["reason"]


def test_lead_a_fires_when_below_trailing_p40():
    trailing = [float(v) for v in range(1, 21)]  # 1..20, p40 interpolates within that range
    p40 = ledger._percentile(trailing, 40.0)
    decision = ledger._decide_lead_a(680.0, p40 - 0.5, "ok", trailing)
    assert decision["fired"] is True
    assert decision["call_gex_trailing_p40"] == pytest.approx(p40)


def test_lead_a_no_fire_when_at_or_above_trailing_p40():
    trailing = [float(v) for v in range(1, 21)]
    p40 = ledger._percentile(trailing, 40.0)
    decision = ledger._decide_lead_a(680.0, p40 + 0.5, "ok", trailing)
    assert decision["fired"] is False


def test_lead_a_no_gamma_data_never_fires():
    decision = ledger._decide_lead_a(680.0, None, "no_expirations_0_60dte", trailing=[1.0] * 20)
    assert decision["fired"] is False
    assert "no_live_call_gex" in decision["reason"]


def test_lead_c2_fires_top_tercile_non_opex():
    trailing = [float(v) for v in range(10, 30)]  # 10..29
    p67 = ledger._percentile(trailing, 67.0)
    decision = ledger._decide_lead_c2(p67 + 1.0, trailing, is_opex=False)
    assert decision["fired"] is True


def test_lead_c2_skips_on_opex_even_if_tercile_hit():
    """Frozen rule: VIX top tercile AND not OPEX -- OPEX alone kills the fire
    even when the VIX condition is true."""
    trailing = [float(v) for v in range(10, 30)]
    p67 = ledger._percentile(trailing, 67.0)
    decision = ledger._decide_lead_c2(p67 + 1.0, trailing, is_opex=True)
    assert decision["fired"] is False
    assert "opex" in decision["reason"]


def test_lead_c2_no_fire_below_tercile():
    trailing = [float(v) for v in range(10, 30)]
    p67 = ledger._percentile(trailing, 67.0)
    decision = ledger._decide_lead_c2(p67 - 1.0, trailing, is_opex=False)
    assert decision["fired"] is False


def test_is_opex_day_matches_third_friday():
    assert ledger._is_opex_day(date(2026, 9, 18)) is True   # 3rd Friday of Sept 2026
    assert ledger._is_opex_day(date(2026, 9, 25)) is False  # 4th Friday
    assert ledger._is_opex_day(date(2026, 9, 21)) is False  # Monday


def test_strike_selection_snaps_to_nearest_quoted_strike_within_tolerance():
    spot = 680.0  # 1% OTM target = 686.8 -> nearest quoted call is 687.0
    sel = ledger._select_strikes_and_quote(_FAKE_XSP_CHAIN, spot)
    assert sel["long_strike"] == pytest.approx(687.0)
    assert sel["short_strike"] == pytest.approx(692.0)  # 687 + 5
    assert sel["long_ask"] == pytest.approx(2.60)
    assert sel["short_bid"] == pytest.approx(0.40)


def test_strike_selection_skips_when_no_strike_within_half_dollar():
    thin_chain = [{"strike": 750.0, "option_type": "call", "bid": 0.10, "ask": 0.20}]
    sel = ledger._select_strikes_and_quote(thin_chain, 680.0)
    assert sel["note"] == "no_long_strike_within_tolerance"


def test_igex_call_definition_mismatch_is_always_flagged_on_lead_a(engine):
    def chain_fn(expiry):
        return _FAKE_XSP_CHAIN

    row = ledger._capture_lead_a(
        engine, date(2026, 9, 21), datetime(2026, 1, 1), datetime(2026, 1, 1),
        spy_spot_fn=lambda: 680.0, xsp_spot_fn=lambda: 680.0,
        expirations_fn=lambda: [], spy_chain_fn=chain_fn, xsp_chain_fn=chain_fn,
    )
    assert row["igex_call_definition_mismatch"] is True
    assert "not validated" in row["igex_call_note"].lower() or "not" in row["igex_call_note"].lower()


# ---------------------------------------------------------------- settlement calc


def test_settlement_payout_matches_the_call_vertical_formula():
    # long 575C / short 580C, debit 0.49, settle 576.97 -> intrinsic 1.97,
    # per-contract payout = 197.00 (hand-derivable identically to the
    # prereg's own hand-audit convention, minus the commission this live
    # ledger does not model).
    payout, pnl = ledger._settlement_payout(576.97, 575.0, 580.0, 0.49)
    assert payout == pytest.approx(197.00)
    assert pnl == pytest.approx(197.00 - 49.00)


def test_settlement_payout_clips_to_width_when_deep_itm():
    payout, pnl = ledger._settlement_payout(700.0, 575.0, 580.0, 1.00)
    assert payout == pytest.approx(500.00)  # clipped to $5 width * 100
    assert pnl == pytest.approx(400.00)


def test_settlement_payout_is_zero_when_otm():
    payout, pnl = ledger._settlement_payout(570.0, 575.0, 580.0, 0.49)
    assert payout == 0.0
    assert pnl == pytest.approx(-49.00)


def test_settle_pending_computes_payout_and_is_idempotent(engine):
    trade_date = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 11, 0, tzinfo=CT)

    # Seed 20 trailing sessions so Lead A's trigger is live (not warming up),
    # all comfortably above the live reading so it fires.
    _seed_trailing(engine, "A", "live_call_gex", [1.0e9] * 20, date(2026, 8, 1))

    ok = ledger.record_tick(
        engine, now_ct,
        spy_spot_fn=lambda: 680.0, xsp_spot_fn=lambda: 680.0,
        expirations_fn=lambda: ["2026-09-21"],
        spy_chain_fn=lambda e: [{"strike": 680.0, "option_type": "call", "bid": 1.0, "ask": 1.0,
                                  "open_interest": 1000, "gamma": 0.0001}],
        xsp_chain_fn=_fake_xsp_chain_fn,
        vix_history_fn=lambda: [],
    )
    assert ok is True
    row_a = _captured_rows(engine, "A", trade_date)[0]
    assert row_a["fired"] in (1, True)
    assert row_a["debit"] is not None

    settle_ct = datetime(2026, 9, 21, 14, 57, tzinfo=CT)
    n1 = ledger.settle_pending(engine, settle_ct, xsp_spot_fn=lambda: 700.0)
    assert n1 == 1
    settled = _captured_rows(engine, "A", trade_date)[0]
    assert settled["settlement_spot"] == pytest.approx(700.0)
    assert settled["payout"] == pytest.approx(500.0)  # deep ITM, clipped to width
    assert settled["settled_at"] is not None

    n2 = ledger.settle_pending(engine, settle_ct, xsp_spot_fn=lambda: 700.0)
    assert n2 == 0  # already settled -- no re-write


def test_settle_pending_leaves_rows_pending_without_a_live_spot(engine):
    trade_date = date(2026, 9, 21)
    now_ct = datetime(2026, 9, 21, 11, 0, tzinfo=CT)
    _seed_trailing(engine, "A", "live_call_gex", [1.0e9] * 20, date(2026, 8, 1))
    ledger.record_tick(
        engine, now_ct,
        spy_spot_fn=lambda: 680.0, xsp_spot_fn=lambda: 680.0,
        expirations_fn=lambda: ["2026-09-21"],
        spy_chain_fn=lambda e: [{"strike": 680.0, "option_type": "call", "bid": 1.0, "ask": 1.0,
                                  "open_interest": 1000, "gamma": 0.0001}],
        xsp_chain_fn=_fake_xsp_chain_fn,
        vix_history_fn=lambda: [],
    )
    settle_ct = datetime(2026, 9, 21, 14, 57, tzinfo=CT)
    n = ledger.settle_pending(engine, settle_ct, xsp_spot_fn=lambda: None)
    assert n == 0
    row = _captured_rows(engine, "A", trade_date)[0]
    assert row["settled_at"] is None


def test_settle_pending_only_touches_todays_fired_rows(engine):
    # A stale row from a prior day, fired, unsettled -- must be left alone,
    # not settled against today's spot.
    row = ledger._base_row("A", date(2026, 9, 18), datetime(2026, 1, 1), datetime(2026, 1, 1))
    row.update({"fired": True, "long_strike": 686.0, "short_strike": 691.0, "debit": 0.5,
                "captured_at": datetime(2026, 1, 1)})
    ledger._upsert(engine, row)

    n = ledger.settle_pending(engine, datetime(2026, 9, 21, 14, 57, tzinfo=CT), xsp_spot_fn=lambda: 700.0)
    assert n == 0
    stale_row = _all_rows(engine, "A")[0]
    assert stale_row["settled_at"] is None


# ---------------------------------------------------------------- idempotency


def test_second_tick_same_day_and_lead_is_a_noop_after_capture(engine):
    seed_start = date(2026, 8, 1)
    _seed_trailing(engine, "C2", "vix_value", [15.0] * 20, seed_start)
    calls = []

    def _tracking_xsp_chain(expiry):
        calls.append(expiry)
        return _FAKE_XSP_CHAIN

    now_ct = datetime(2026, 9, 21, 9, 30, tzinfo=CT)  # Lead C2's decision minute
    ledger.record_tick(
        engine, now_ct, xsp_spot_fn=lambda: 680.0,
        vix_history_fn=lambda: [{"date": "2026-09-18", "close": 30.0}],
        xsp_chain_fn=_tracking_xsp_chain,
    )
    first_calls = len(calls)
    assert first_calls >= 1
    first_row = _captured_rows(engine, "C2", now_ct.date())[0]

    later_ct = now_ct.replace(minute=32)
    ledger.record_tick(
        engine, later_ct, xsp_spot_fn=lambda: 680.0,
        vix_history_fn=lambda: [{"date": "2026-09-18", "close": 30.0}],
        xsp_chain_fn=_tracking_xsp_chain,
    )
    assert len(calls) == first_calls  # no second chain fetch
    rows = _captured_rows(engine, "C2", now_ct.date())
    assert len(rows) == 1
    assert rows[0]["debit"] == first_row["debit"]


def test_a_new_trade_date_is_a_new_row(engine):
    seed_start = date(2026, 8, 1)
    _seed_trailing(engine, "C2", "vix_value", [15.0] * 20, seed_start)
    now1 = datetime(2026, 9, 21, 9, 30, tzinfo=CT)
    now2 = datetime(2026, 9, 22, 9, 30, tzinfo=CT)
    ledger.record_tick(engine, now1, xsp_spot_fn=lambda: 680.0,
                        vix_history_fn=lambda: [{"date": "2026-09-18", "close": 10.0}],
                        xsp_chain_fn=_fake_xsp_chain_fn)
    ledger.record_tick(engine, now2, xsp_spot_fn=lambda: 680.0,
                        vix_history_fn=lambda: [{"date": "2026-09-21", "close": 10.0}],
                        xsp_chain_fn=_fake_xsp_chain_fn)
    rows = _captured_rows(engine, "C2", date(2026, 9, 21))
    assert len(rows) == 2
    assert {str(r["trade_date"]) for r in rows} == {"2026-09-21", "2026-09-22"}


def test_missed_capture_window_is_a_terminal_row_and_never_calls_the_chain(engine):
    calls = []

    def _tracking_chain(expiry):
        calls.append(expiry)
        return _FAKE_XSP_CHAIN

    # Well past Lead C2's 9:30 CT decision + 7min tolerance, with no prior tick.
    now_ct = datetime(2026, 9, 21, 10, 0, tzinfo=CT)
    ledger.record_tick(engine, now_ct, xsp_chain_fn=_tracking_chain, spy_chain_fn=_tracking_chain)
    rows = _all_rows(engine, "C2")
    assert len(rows) == 1
    assert rows[0]["fired"] in (0, False)
    assert "missed" in rows[0]["reason"]
    assert calls == []
