"""EMBER TVBook forward call log — table create, idempotency, unarmed logging,
and failure isolation.

WHY THIS TABLE EXISTS: TVBook's long/short call comes from TradingVolatility's
own proprietary recommended_direction/trade_bias, which has no history of its
own. `ember_tv_call_log` is the point-in-time record needed to score that call
later — see backend/ember/tv_call_log.py's module docstring for the full
design (two row flavors, one table, idempotent on (run_id, endpoint, ticker)).

🚨 THE ONE THING THIS FILE MUST PROVE: nothing here ever checks
EMBER_TVBOOK_LIVE/EMBER_TVBOOK_ENABLED or any other arming flag — logging is
unconditional instrumentation, not gated trading logic. See
test_logging_ignores_arming_env_entirely and
test_fleet_runs_the_scanner_subprocess_while_unarmed below.
"""
from __future__ import annotations

import csv
from datetime import date

import pytest
from sqlalchemy import create_engine, text

from backend.ember import tv_call_log as cl

TABLE = cl.TABLE


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    cl.ensure_table(eng)
    return eng


def _all_rows(engine):
    with engine.begin() as conn:
        return conn.execute(text(f"SELECT * FROM {TABLE}")).mappings().all()


# ---------------------------------------------------------------- table create

def test_ensure_table_is_idempotent(engine):
    cl.ensure_table(engine)   # second call must not raise / must not duplicate the table
    cl.ensure_table(engine)
    with engine.begin() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"
        ), {"t": TABLE}).scalar_one()
    assert n == 1


def test_ensure_table_on_a_missing_table_is_a_noop_until_the_first_write(monkeypatch):
    """A caller that never had a chance to call ensure_table() directly (e.g.
    log_call on a fresh DB) still gets the table auto-created — 'auto-create
    on first use', not a migration step someone has to remember."""
    eng = create_engine("sqlite:///:memory:", future=True)
    with eng.begin() as conn:
        n = conn.execute(text(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=:t"
        ), {"t": TABLE}).scalar_one()
    assert n == 0
    ok = cl.log_call(eng, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups",
                      ticker="AAPL", rank=1)
    assert ok is True
    assert len(_all_rows(eng)) == 1


# ---------------------------------------------------------------- basic insert

def test_log_call_writes_the_fields_it_is_given(engine):
    ok = cl.log_call(
        engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups", ticker="NVDA",
        rank=3, recommended_direction="long", trade_bias="bullish", opportunity_score=8.7,
        context={"price": 190.5, "flip": 185.0, "put_wall": 180.0, "call_wall": 200.0,
                 "iv_rank": 62.0, "em_1d_pct": 1.5, "em_1w_pct": 3.2},
        would_setup=True, side="long", entry=190.5, stop=182.0, target=205.0, stock_rr=2.1,
        liquid=True, structure="vertical", contract="NVDA 2026-10-30 190/200C",
        debit=3.5, cost_usd=350, note=None, raw_item={"ticker": "NVDA", "opportunity_score": 8.7},
    )
    assert ok is True
    rows = _all_rows(engine)
    assert len(rows) == 1
    r = rows[0]
    assert r["ticker"] == "NVDA"
    assert r["endpoint"] == "top-setups"
    assert r["rank"] == 3
    assert r["recommended_direction"] == "long"
    assert r["trade_bias"] == "bullish"
    assert r["price"] == 190.5
    assert r["put_wall"] == 180.0
    assert r["call_wall"] == 200.0
    assert bool(r["would_setup"]) is True
    assert r["contract"] == "NVDA 2026-10-30 190/200C"
    assert "opportunity_score" in r["raw_item_json"]
    assert "put_wall" in r["raw_context_json"]


def test_log_call_requires_a_ticker_and_endpoint(engine):
    assert cl.log_call(engine, run_id="run-1", scan_date=date.today(), endpoint="", ticker="AAPL") is False
    assert cl.log_call(engine, run_id="run-1", scan_date=date.today(), endpoint="top-setups", ticker="") is False
    assert len(_all_rows(engine)) == 0


# ---------------------------------------------------------------- idempotency

def test_idempotent_per_run_endpoint_ticker(engine):
    """Same (run_id, endpoint, ticker) written twice in one run upserts one
    row, refreshed to the second call's values — not a duplicate."""
    cl.log_call(engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups",
                ticker="TSLA", rank=5, recommended_direction="short")
    cl.log_call(engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups",
                ticker="TSLA", rank=5, recommended_direction="long")
    rows = _all_rows(engine)
    assert len(rows) == 1
    assert rows[0]["recommended_direction"] == "long"


def test_idempotency_key_is_endpoint_scoped_not_ticker_alone(engine):
    """The SAME ticker on two different endpoints in the same run is two
    distinct rows — endpoint is part of the identity, not metadata."""
    cl.log_call(engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups", ticker="MSFT")
    cl.log_call(engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="momentum_breakout", ticker="MSFT")
    rows = _all_rows(engine)
    assert len(rows) == 2
    assert {r["endpoint"] for r in rows} == {"top-setups", "momentum_breakout"}


def test_a_new_run_id_is_a_new_row_not_an_overwrite(engine):
    """Idempotency is scoped to ONE run — the next scheduled scan is a new
    run_id and must add rows, never collapse into the prior tick's."""
    cl.log_call(engine, run_id="run-1", scan_date=date(2026, 9, 28), endpoint="top-setups", ticker="MSFT")
    cl.log_call(engine, run_id="run-2", scan_date=date(2026, 9, 28), endpoint="top-setups", ticker="MSFT")
    rows = _all_rows(engine)
    assert len(rows) == 2
    assert {r["run_id"] for r in rows} == {"run-1", "run-2"}


# ---------------------------------------------------------------- log_source_items

def test_log_source_items_ranks_by_list_order_and_endpoint_label(engine):
    items = [
        {"ticker": "AAA", "opportunity_score": 9.1, "recommended_direction": "long"},
        {"ticker": "BBB", "opportunity_score": 7.4, "trade_bias": "bearish"},
        {"ticker": "CCC", "opportunity_score": 5.0},
    ]
    n = cl.log_source_items(engine, run_id="run-1", scan_date=date(2026, 9, 28),
                             endpoint=cl.endpoint_label("idea"), items=items)
    assert n == 3
    rows = {r["ticker"]: r for r in _all_rows(engine)}
    assert rows["AAA"]["rank"] == 1 and rows["AAA"]["endpoint"] == "top-setups"
    assert rows["BBB"]["rank"] == 2 and rows["BBB"]["trade_bias"] == "bearish"
    assert rows["CCC"]["rank"] == 3


def test_log_source_items_skips_items_with_no_ticker(engine):
    n = cl.log_source_items(engine, run_id="run-1", scan_date=date.today(),
                             endpoint="income-setups", items=[{"opportunity_score": 1.0}, {"ticker": "SPY"}])
    assert n == 1
    assert [r["ticker"] for r in _all_rows(engine)] == ["SPY"]


def test_endpoint_label_maps_idea_and_income_passes_presets_through():
    assert cl.endpoint_label("idea") == "top-setups"
    assert cl.endpoint_label("income") == "income-setups"
    assert cl.endpoint_label("bottoming_reversal") == "bottoming_reversal"


# ---------------------------------------------------------------- log_evaluation

def test_log_evaluation_records_a_setup_that_would_have_fired(engine):
    rr_row = {"dir": "long", "price": 100.0, "stop": 95.0, "target": 115.0, "stock_rr": 3.0,
              "liquid": True, "structure": "single", "contract": "AAA 2026-10-30 100C",
              "debit": 2.5, "cost_usd": 250, "liq_note": None}
    n = cl.log_evaluation(engine, run_id="run-1", scan_date=date(2026, 9, 28), ticker="AAA",
                           context={"price": 100.0}, rr_row=rr_row, rr_bucket="setups",
                           bounce_row=None, bounce_bucket=None)
    assert n == 2
    rows = {r["endpoint"]: r for r in _all_rows(engine)}
    assert bool(rows["rr_eval"]["would_setup"]) is True
    assert rows["rr_eval"]["structure"] == "single"
    assert rows["rr_eval"]["cost_usd"] == 250
    assert bool(rows["bounce_eval"]["would_setup"]) is False
    assert rows["bounce_eval"]["note"] == "no bounce signal"


def test_log_evaluation_illiquid_setup_still_would_setup_true(engine):
    """>=2:1 on TV's own walls IS a setup even when the liquidity gate later
    disqualifies it from being traded — `liquid=False` records that
    separately, it does not change `would_setup`."""
    rr_row = {"dir": "short", "price": 50.0, "stop": 55.0, "target": 35.0, "stock_rr": 3.0,
              "liquid": False, "structure": "single", "liq_note": "thin OI"}
    n = cl.log_evaluation(engine, run_id="run-1", scan_date=date(2026, 9, 28), ticker="BBB",
                           context=None, rr_row=rr_row, rr_bucket="illiquid",
                           bounce_row=None, bounce_bucket=None)
    assert n == 2
    row = {r["endpoint"]: r for r in _all_rows(engine)}["rr_eval"]
    assert bool(row["would_setup"]) is True
    assert bool(row["liquid"]) is False
    assert row["note"] == "thin OI"


def test_log_evaluation_with_no_direction_records_both_rows_as_no_setup(engine):
    """A candidate with no direction and no bounce signal still gets a row on
    both endpoints — the record of 'evaluated, nothing fired' is the point;
    silently skipping it would make the table look survivorship-biased."""
    n = cl.log_evaluation(engine, run_id="run-1", scan_date=date(2026, 9, 28), ticker="CCC",
                           context={"price": 42.0}, rr_row=None, rr_bucket=None,
                           bounce_row=None, bounce_bucket=None, nodata_reason="no direction")
    assert n == 2
    rows = {r["endpoint"]: r for r in _all_rows(engine)}
    assert bool(rows["rr_eval"]["would_setup"]) is False
    assert rows["rr_eval"]["note"] == "no direction"
    assert bool(rows["bounce_eval"]["would_setup"]) is False
    assert rows["bounce_eval"]["price"] == 42.0   # context still carried even with no row


def test_log_evaluation_bounce_pcs_structure_maps_credit_and_max_loss(engine):
    bounce_row = {"dir": "long", "price": 60.0, "stop": 57.0, "target": 70.0, "stock_rr": 3.3,
                  "liquid": True, "structure": "pcs", "pcs_credit": 0.85, "pcs_max_loss": 165.0,
                  "tier": "setup", "pcs_note": None}
    n = cl.log_evaluation(engine, run_id="run-1", scan_date=date(2026, 9, 28), ticker="DDD",
                           context=None, rr_row=None, rr_bucket=None,
                           bounce_row=bounce_row, bounce_bucket="bounce_rows")
    assert n == 2
    row = {r["endpoint"]: r for r in _all_rows(engine)}["bounce_eval"]
    assert bool(row["would_setup"]) is True
    assert row["debit"] == 0.85
    assert row["cost_usd"] == 165.0


def test_log_evaluation_bounce_marginal_tier_is_not_a_setup(engine):
    """`bucket == "bounce_rows"` alone is not enough — marginal (1:1-2:1) rows
    also land in bounce_rows; only tier == "setup" (>=2:1) counts."""
    bounce_row = {"dir": "long", "price": 60.0, "stop": 58.0, "target": 65.0, "stock_rr": 1.4,
                  "liquid": None, "structure": "call", "tier": "marginal"}
    cl.log_evaluation(engine, run_id="run-1", scan_date=date(2026, 9, 28), ticker="EEE",
                       context=None, rr_row=None, rr_bucket=None,
                       bounce_row=bounce_row, bounce_bucket="bounce_rows")
    row = {r["endpoint"]: r for r in _all_rows(engine)}["bounce_eval"]
    assert bool(row["would_setup"]) is False


# ---------------------------------------------------------------- unarmed logging

def test_logging_ignores_arming_env_entirely(engine, monkeypatch):
    """🚨 THE REQUIREMENT: this module has no arming concept at all. Setting
    every EMBER TVBOOK env flag to disarmed/paused must not change whether a
    call is recorded — there is no code path here that reads them."""
    monkeypatch.setenv("EMBER_TVBOOK_LIVE", "0")
    monkeypatch.setenv("EMBER_TVBOOK_ENABLED", "0")
    ok = cl.log_call(engine, run_id="run-1", scan_date=date.today(), endpoint="top-setups", ticker="SPY")
    assert ok is True
    assert len(_all_rows(engine)) == 1


def test_none_of_the_public_functions_take_a_live_or_armed_parameter():
    """Guards against a future edit quietly re-introducing an arming gate."""
    import inspect
    for fn in (cl.log_call, cl.log_source_items, cl.log_evaluation, cl.ensure_table, cl.export_csv):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"live", "armed", "dry_run", "cfg"}), fn.__name__


def test_fleet_runs_the_scanner_subprocess_while_unarmed(monkeypatch, tmp_path):
    """Orchestration-level proof: fleet_runtime._run_tv_scanner() (which
    invokes tv_scanner.py, where this module's hooks live) fires whenever
    tv_book is ENABLED, regardless of EMBER_TVBOOK_LIVE. `_validate_live()`
    only raises when `live=True` and the Render persistent-disk paths are
    missing — with live=False it is a no-op, so the scan (and every
    tv_call_log write inside it) runs while EMBER is paused/live=0."""
    from dataclasses import replace

    from backend.ember import fleet_runtime as fleet

    monkeypatch.setenv("EMBER_TVBOOK_ENABLED", "1")
    monkeypatch.setenv("EMBER_TVBOOK_LIVE", "0")   # unarmed / paper

    state_path = tmp_path / "state.json"
    state_path.write_text('{"positions": [], "in_flight": {}}', encoding="utf-8")
    original = fleet.SPECS["tv_book"]
    spec = replace(original, state_path=state_path,
                   config_loader=lambda: fleet.tv_book.Cfg(), runner=lambda *a, **k: 0)
    monkeypatch.setitem(fleet.SPECS, "tv_book", spec)
    monkeypatch.setattr(fleet, "_hydrate", lambda s: "disk")
    monkeypatch.setattr(fleet, "_dependency_gaps", lambda s: [])
    monkeypatch.setattr(fleet, "_acquire_lock", lambda name, **kwargs: object())
    monkeypatch.setattr(fleet, "_release_lock", lambda _db, _name: None)
    monkeypatch.setattr(fleet.xsp_runtime, "_prepare_claude_home", lambda: None)
    monkeypatch.setattr(fleet.xsp_runtime, "_config_put", lambda *a, **k: None)
    scanner_calls = []
    monkeypatch.setattr(fleet, "_run_tv_scanner", lambda: scanner_calls.append(True))

    fleet.run_tv_book()

    assert scanner_calls == [True]   # the scan ran even though EMBER_TVBOOK_LIVE=0
