"""The /hunt page's backend: /confirm-history (a read-only list of every day
the two-stage confirmation watcher has recorded) plus the stage-4 additions —
the forward-only paper book (risk_confirm_paper) and the flow-at-fire ledger
(risk_flow_intraday / risk_confirm_flow_at_fire).

Everything else /hunt shows (today's flag, today's confirm state, the
playbook, the alert directory) already exists on /session and as static copy.
"""
import asyncio
from datetime import date, datetime, timedelta

import pytest

from backend import routes_risk as R
from backend import routes as ROUTES

CT = R.CT


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture
def confirm_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db import Base
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(R, "SessionLocal", Session)
    return Session


def _row(Session, **kw):
    db = Session()
    row = R.RiskConfirmState(**kw)
    db.add(row)
    db.commit()
    db.close()


def test_no_database_reports_unavailable_not_a_crash(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", None)
    out = _run(R.confirm_history())
    assert out["status"] == "unavailable"
    assert out["rows"] == []


def test_an_empty_table_is_an_empty_list_not_an_error(confirm_db):
    out = _run(R.confirm_history())
    assert out["status"] == "ok"
    assert out["rows"] == []


def test_a_fired_down_day_reports_a_positive_outcome_when_it_kept_falling(confirm_db):
    _row(confirm_db, d=date(2026, 8, 17), armed="yes", putcall_z=2.72,
         ref_spot=775.50, run_min=772.51, run_max=775.50,
         fired_dir="DOWN", fired_at=datetime(2026, 8, 17, 11, 55),
         fired_spot=774.68, close_spot=772.67)
    rows = _run(R.confirm_history())["rows"]
    assert len(rows) == 1
    r = rows[0]
    assert r["fired_dir"] == "DOWN"
    assert r["ref_spot"] == 775.50
    assert r["fired_at"] == "2026-08-17T11:55:00"
    # it kept moving DOWN after the fire (772.67 < 774.68), so the SIGNED
    # outcome — positive means "continued in the fired direction" — is > 0
    assert r["outcome_pct"] > 0
    assert r["outcome_pct"] == pytest.approx(
        (774.68 - 772.67) / 774.68 * 100, abs=1e-3)


def test_an_up_day_that_reversed_reports_a_negative_outcome(confirm_db):
    """Signed in the fired direction: an UP confirmation that gives it all
    back before the close must NOT read as a win."""
    _row(confirm_db, d=date(2026, 8, 19), armed="yes", putcall_z=1.9,
         ref_spot=700.00, run_min=700.00, run_max=701.00,
         fired_dir="UP", fired_at=datetime(2026, 8, 19, 11, 0),
         fired_spot=701.00, close_spot=699.50)
    r = _run(R.confirm_history())["rows"][0]
    assert r["outcome_pct"] < 0


def test_a_day_that_never_fired_still_appears_with_no_outcome(confirm_db):
    """Every session the watcher ran belongs on the reviewable list, not just
    the ones that fired — 'no confirm' is itself a fact worth reading."""
    _row(confirm_db, d=date(2026, 8, 21), armed="no", putcall_z=0.4,
         ref_spot=780.00, run_min=779.50, run_max=780.20)
    r = _run(R.confirm_history())["rows"][0]
    assert r["fired_dir"] is None
    assert r["outcome_pct"] is None


def test_a_row_missing_close_spot_does_not_crash_and_has_no_outcome(confirm_db):
    """The close is filled by a separate end-of-day job; a firing recorded
    mid-session and read before that job runs must degrade gracefully."""
    _row(confirm_db, d=date(2026, 8, 24), armed="yes", putcall_z=2.1,
         ref_spot=750.00, run_min=748.00, run_max=750.00,
         fired_dir="DOWN", fired_at=datetime(2026, 8, 24, 10, 40),
         fired_spot=748.50, close_spot=None)
    r = _run(R.confirm_history())["rows"][0]
    assert r["outcome_pct"] is None


def test_newest_first(confirm_db):
    _row(confirm_db, d=date(2026, 8, 10), armed="no")
    _row(confirm_db, d=date(2026, 8, 12), armed="no")
    _row(confirm_db, d=date(2026, 8, 11), armed="no")
    rows = _run(R.confirm_history())["rows"]
    assert [r["d"] for r in rows] == ["2026-08-12", "2026-08-11", "2026-08-10"]


def test_limit_is_respected_and_bounded(confirm_db):
    for i in range(5):
        _row(confirm_db, d=date(2026, 8, 1 + i), armed="no")
    assert len(_run(R.confirm_history(limit=2))["rows"]) == 2
    # an absurd limit must not blow past the module's hard cap of 500
    out = _run(R.confirm_history(limit=10_000))
    assert out["status"] == "ok"


def test_a_broken_query_degrades_to_unavailable_not_a_500(confirm_db, monkeypatch):
    class _BoomSession:
        def __call__(self):
            raise RuntimeError("db is down")
    monkeypatch.setattr(R, "SessionLocal", _BoomSession())
    out = _run(R.confirm_history())
    assert out["status"] == "unavailable"
    assert out["rows"] == []


# ── Paper book — stage 4 ─────────────────────────────────────────────────
# Everything below is forward-only: PAPER_BOOK_START gates every write, so
# every test uses a date on or after it rather than hardcoding an arbitrary
# calendar date.

FIRE_D = R.PAPER_BOOK_START


def _opt(option_type, strike, bid, ask, last=None, volume=10):
    return {"option_type": option_type, "strike": strike, "bid": bid,
            "ask": ask, "last": last if last is not None else (bid + ask) / 2,
            "volume": volume}


def _mock_tradier(expirations, chains):
    """Fake replacement for backend.routes._tradier_get, keyed by path."""
    async def fake(request, path, params=None):
        if path == "/markets/options/expirations":
            return {"expirations": {"date": expirations}}
        if path == "/markets/options/chains":
            exp = (params or {}).get("expiration")
            return {"options": {"option": chains.get(exp, [])}}
        raise AssertionError(f"unexpected Tradier path in test: {path}")
    return fake


def _mock_quote(spot):
    async def fake(request, symbol):
        return {"last": spot}
    return fake


def test_paper_row_created_on_an_up_fire(confirm_db, monkeypatch):
    exp = FIRE_D.isoformat()
    chain = [
        _opt("call", 765, bid=0.85, ask=0.90),
        _opt("call", 767, bid=0.10, ask=0.12),
        _opt("put", 765, bid=0.50, ask=0.55),
    ]
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([exp], {exp: chain}))
    hit = {"dir": "UP", "spot": 765.3, "at": datetime(2026, 9, 2, 11, 20)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))

    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.fired_dir == "UP"
    assert row.expiry == exp
    assert row.long_strike == 765 and row.short_strike == 767
    assert row.long_ask == pytest.approx(0.90)
    assert row.short_bid == pytest.approx(0.10)
    assert row.debit == pytest.approx(0.80)
    assert row.skipped_reason is None
    assert row.contracts == R.PAPER_CONTRACTS


def test_paper_row_created_on_a_down_fire(confirm_db, monkeypatch):
    exp = FIRE_D.isoformat()
    chain = [
        _opt("put", 748, bid=0.75, ask=0.80),
        _opt("put", 746, bid=0.15, ask=0.18),
    ]
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([exp], {exp: chain}))
    hit = {"dir": "DOWN", "spot": 747.6, "at": datetime(2026, 9, 2, 10, 40)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))

    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.fired_dir == "DOWN"
    # nearest whole dollar to 747.6 is 748; short is long-2 on a DOWN fire
    assert row.long_strike == 748 and row.short_strike == 746
    assert row.debit == pytest.approx(0.80 - 0.15)
    assert row.skipped_reason is None


def test_skip_when_todays_expiry_is_not_in_the_chain(confirm_db, monkeypatch):
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier(["2099-01-01"], {}))
    hit = {"dir": "UP", "spot": 700.0, "at": datetime(2026, 9, 2, 11, 0)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.skipped_reason == "no_0dte"
    assert row.debit is None


def test_skip_when_a_quote_is_missing(confirm_db, monkeypatch):
    exp = FIRE_D.isoformat()
    # only the long strike is quoted; the short leg never traded today
    chain = [_opt("call", 700, bid=0.60, ask=0.65)]
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([exp], {exp: chain}))
    hit = {"dir": "UP", "spot": 700.0, "at": datetime(2026, 9, 2, 11, 0)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.skipped_reason == "missing_quote"


def test_skip_when_debit_is_nonpositive(confirm_db, monkeypatch):
    exp = FIRE_D.isoformat()
    # long ask below short bid -> a negative debit, never a real trade
    chain = [
        _opt("call", 700, bid=0.10, ask=0.10),
        _opt("call", 702, bid=0.20, ask=0.22),
    ]
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([exp], {exp: chain}))
    hit = {"dir": "UP", "spot": 700.0, "at": datetime(2026, 9, 2, 11, 0)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.skipped_reason == "debit_nonpositive"


def test_skip_when_debit_is_at_or_above_the_wing_width(confirm_db, monkeypatch):
    exp = FIRE_D.isoformat()
    chain = [
        _opt("call", 700, bid=2.00, ask=2.50),
        _opt("call", 702, bid=0.10, ask=0.12),
    ]
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([exp], {exp: chain}))
    hit = {"dir": "UP", "spot": 700.0, "at": datetime(2026, 9, 2, 11, 0)}
    _run(R.paper_record_fire(object(), FIRE_D, hit))
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.skipped_reason == "debit_too_wide"


def test_paper_record_fire_is_a_noop_before_book_start(confirm_db, monkeypatch):
    monkeypatch.setattr(ROUTES, "_tradier_get",
                        _mock_tradier([], {}))
    hit = {"dir": "UP", "spot": 700.0, "at": datetime(2026, 8, 20, 11, 0)}
    _run(R.paper_record_fire(object(), date(2026, 8, 20), hit))
    db = confirm_db()
    assert db.query(R.RiskConfirmPaper).count() == 0
    db.close()


def _paper_row(Session, **kw):
    db = Session()
    row = R.RiskConfirmPaper(**kw)
    db.add(row)
    db.commit()
    db.close()
    return row


def test_settlement_up_fire_caps_at_the_wing_width(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="UP", close_spot=770.00)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1)
    n = R.paper_settle_pending()
    assert n == 1
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    # close (770) is well past the short strike -> intrinsic caps at $2
    assert row.settle_value == pytest.approx(2.0)
    assert row.pnl == pytest.approx((2.0 - 0.80) * 100)
    assert row.settled_at is not None


def test_settlement_down_fire_caps_at_the_wing_width(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="DOWN", close_spot=740.00)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="DOWN", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=748.0, short_strike=746.0, debit=0.65, contracts=1)
    R.paper_settle_pending()
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.settle_value == pytest.approx(2.0)
    assert row.pnl == pytest.approx((2.0 - 0.65) * 100)


def test_settlement_expires_worthless_at_zero(confirm_db):
    # UP fire, but the close never got there: long strike above the close
    _row(confirm_db, d=FIRE_D, fired_dir="UP", close_spot=764.00)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1)
    R.paper_settle_pending()
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.settle_value == pytest.approx(0.0)
    assert row.pnl == pytest.approx(-0.80 * 100)


def test_settlement_is_idempotent_and_skips_already_settled_rows(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="UP", close_spot=770.00)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1)
    first = R.paper_settle_pending()
    second = R.paper_settle_pending()
    assert first == 1
    assert second == 0


def test_settlement_skips_a_row_with_no_close_yet(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="UP", close_spot=None)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1)
    n = R.paper_settle_pending()
    assert n == 0
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.settled_at is None


def test_settlement_skips_a_skipped_row(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="UP", close_spot=770.00)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              skipped_reason="no_0dte")
    n = R.paper_settle_pending()
    assert n == 0


def test_confirm_record_close_settles_paper_rows_for_that_date(confirm_db):
    _row(confirm_db, d=FIRE_D, fired_dir="UP", ref_spot=765.0, run_min=765.0, run_max=766.0)
    _paper_row(confirm_db, d=FIRE_D, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1)
    R.confirm_record_close(FIRE_D, 770.00)
    db = confirm_db()
    row = db.query(R.RiskConfirmPaper).one()
    db.close()
    assert row.settled_at is not None
    assert row.pnl == pytest.approx((2.0 - 0.80) * 100)


def test_paper_book_empty_state(confirm_db):
    out = _run(R.paper_book())
    assert out["start_balance"] == R.PAPER_START_BALANCE
    assert out["running_balance"] == R.PAPER_START_BALANCE
    assert out["pnl_total"] == 0.0
    assert out["fires"] == 0
    assert out["rows"] == []
    assert out["gate"]["fires_required"] == 40
    assert out["gate"]["deadline"] == "2027-12-31"


def test_paper_book_no_database_degrades_gracefully(monkeypatch):
    monkeypatch.setattr(R, "SessionLocal", None)
    out = _run(R.paper_book())
    assert out["running_balance"] == R.PAPER_START_BALANCE
    assert out["rows"] == []


def test_paper_book_aggregates_running_balance_and_stats(confirm_db):
    d1, d2, d3 = FIRE_D, FIRE_D + timedelta(days=1), FIRE_D + timedelta(days=2)
    _paper_row(confirm_db, d=d1, fired_dir="UP", fired_at=datetime(2026, 9, 2, 11, 0),
              long_strike=765.0, short_strike=767.0, debit=0.80, contracts=1,
              settle_value=2.0, pnl=120.0, settled_at=datetime(2026, 9, 2, 15, 5))
    _paper_row(confirm_db, d=d2, fired_dir="DOWN", fired_at=datetime(2026, 9, 3, 10, 40),
              long_strike=748.0, short_strike=746.0, debit=0.65, contracts=1,
              settle_value=0.0, pnl=-65.0, settled_at=datetime(2026, 9, 3, 15, 5))
    _paper_row(confirm_db, d=d3, fired_dir="UP", fired_at=datetime(2026, 9, 4, 11, 0),
              skipped_reason="no_0dte")
    out = _run(R.paper_book())
    assert out["fires"] == 3
    assert out["settled"] == 2
    assert out["skipped"] == 1
    assert out["wins"] == 1
    assert out["win_rate"] == pytest.approx(0.5)
    assert out["pnl_total"] == pytest.approx(55.0)
    assert out["running_balance"] == pytest.approx(R.PAPER_START_BALANCE + 55.0)
    assert out["median_pnl"] == pytest.approx((120.0 + -65.0) / 2)
    assert out["worst_pnl"] == pytest.approx(-65.0)
    assert out["best_pnl"] == pytest.approx(120.0)
    # newest first
    assert [r["date"] for r in out["rows"]] == [d3.isoformat(), d2.isoformat(), d1.isoformat()]
    # skipped row shows the reason and carries the prior running balance
    skipped_row = next(r for r in out["rows"] if r["date"] == d3.isoformat())
    assert skipped_row["skipped_reason"] == "no_0dte"
    assert skipped_row["running_balance"] == pytest.approx(R.PAPER_START_BALANCE + 55.0)
    # the first (oldest) row's running balance reflects only its own pnl
    first_row = next(r for r in out["rows"] if r["date"] == d1.isoformat())
    assert first_row["running_balance"] == pytest.approx(R.PAPER_START_BALANCE + 120.0)
    assert first_row["strikes"] == "C 765/767"


# ── Flow-at-fire ledger — stage 4 ────────────────────────────────────────

def test_bucket_expirations_sorts_into_the_right_tenors():
    today = date(2026, 9, 2)
    exps = [
        "2026-09-02",   # 0dte
        "2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06",  # 1-5d (4 candidates)
        "2026-09-10", "2026-09-12", "2026-09-15", "2026-09-19", "2026-09-22",  # 6-20d
        "2026-09-25", "2026-10-20", "2026-12-18",  # far
    ]
    out = R._bucket_expirations(today, exps)
    assert out["0dte"] == ["2026-09-02"]
    assert len(out["1_5d"]) <= 3
    assert set(out["1_5d"]).issubset({"2026-09-03", "2026-09-04", "2026-09-05", "2026-09-06"})
    assert len(out["6_20d"]) <= 3
    assert len(out["far"]) <= 2
    # far includes the nearest >20d expiry
    assert out["far"][0] == "2026-09-25"


def test_bucket_expirations_drops_malformed_dates():
    out = R._bucket_expirations(date(2026, 9, 2), ["not-a-date", "2026-09-02"])
    assert out["0dte"] == ["2026-09-02"]


def test_chain_flow_stats_buy_share_from_last_vs_quote():
    opts = [
        # last==ask -> a clean buy
        _opt("call", 700, bid=0.80, ask=1.00, last=1.00, volume=100),
        # last==bid -> a clean sell, no buy contribution
        _opt("call", 702, bid=0.30, ask=0.50, last=0.30, volume=50),
        _opt("put", 698, bid=0.40, ask=0.60, last=0.60, volume=20),
    ]
    stats = R._chain_flow_stats(opts)
    assert stats["call_vol"] == 150
    assert stats["put_vol"] == 20
    # 100 buy-volume out of 150 total call volume
    assert stats["call_buy_share"] == pytest.approx(100 / 150)
    assert stats["put_buy_share"] == pytest.approx(1.0)
    assert stats["call_notional"] == pytest.approx(100 * 0.90 * 100 + 50 * 0.40 * 100)


def test_chain_flow_stats_null_share_on_zero_volume():
    stats = R._chain_flow_stats([_opt("call", 700, bid=0.80, ask=1.00, volume=0)])
    assert stats["call_vol"] == 0
    assert stats["call_buy_share"] is None
    assert stats["put_buy_share"] is None


def test_capture_flow_intraday_writes_one_row_per_tenor(confirm_db, monkeypatch):
    d = FIRE_D
    exp0 = d.isoformat()
    monkeypatch.setattr(ROUTES, "_get_quote", _mock_quote(700.0))
    monkeypatch.setattr(ROUTES, "_tradier_get", _mock_tradier(
        [exp0],
        {exp0: [_opt("call", 700, bid=0.80, ask=1.00, last=1.00, volume=100)]},
    ))
    _run(R.capture_flow_intraday(object(), datetime(2026, 9, 2, 10, 20)))
    db = confirm_db()
    rows = db.query(R.RiskFlowIntraday).filter(R.RiskFlowIntraday.d == d).all()
    db.close()
    tenors = {r.tenor for r in rows}
    assert tenors == set(R.FLOW_TENORS)
    zero_row = next(r for r in rows if r.tenor == "0dte")
    assert zero_row.call_vol == 100
    assert zero_row.spot == pytest.approx(700.0)


def test_capture_flow_intraday_is_a_noop_before_book_start(confirm_db, monkeypatch):
    monkeypatch.setattr(ROUTES, "_get_quote", _mock_quote(700.0))
    monkeypatch.setattr(ROUTES, "_tradier_get", _mock_tradier([], {}))
    _run(R.capture_flow_intraday(object(), datetime(2026, 8, 20, 10, 20)))
    db = confirm_db()
    assert db.query(R.RiskFlowIntraday).count() == 0
    db.close()


def _flow_row(Session, **kw):
    db = Session()
    row = R.RiskFlowIntraday(**kw)
    db.add(row)
    db.commit()
    db.close()


def test_flow_record_at_fire_computes_deltas_from_the_prior_reading(confirm_db, monkeypatch):
    d = FIRE_D
    # flow_mix_z is meant to be the same figure /session reports at 10:00 —
    # isolate that dependency here rather than replaying the whole baseline
    # CSV + snapshot chain _flow_mix_z_for pulls it from.
    monkeypatch.setattr(R, "_flow_mix_z_for", lambda dd: 2.5)
    _flow_row(confirm_db, ts=datetime(2026, 9, 2, 10, 10), d=d, tenor="0dte",
             n_expiries=1, call_vol=100, put_vol=50, call_notional=9000.0,
             put_notional=4500.0, call_buy_share=0.6, put_buy_share=0.4, spot=700.0)
    _flow_row(confirm_db, ts=datetime(2026, 9, 2, 10, 20), d=d, tenor="0dte",
             n_expiries=1, call_vol=180, put_vol=90, call_notional=16000.0,
             put_notional=8200.0, call_buy_share=0.65, put_buy_share=0.45, spot=701.0)
    hit = {"dir": "UP", "spot": 701.0, "at": datetime(2026, 9, 2, 10, 21)}
    R.flow_record_at_fire(d, hit)

    db = confirm_db()
    row = db.query(R.RiskConfirmFlowAtFire).filter(
        R.RiskConfirmFlowAtFire.tenor == "0dte").one()
    db.close()
    assert row.call_vol == 180 and row.put_vol == 90            # cumulative = latest
    assert row.call_vol_d == 80 and row.put_vol_d == 40          # delta vs prior
    assert row.call_notional_d == pytest.approx(7000.0)
    assert row.put_notional_d == pytest.approx(3700.0)
    assert row.call_buy_share == pytest.approx(0.65)             # latest, not a delta
    assert row.flow_mix_z == pytest.approx(2.5)                  # reused _flow_mix_z_for


def test_flow_record_at_fire_null_deltas_with_no_prior_reading(confirm_db):
    d = FIRE_D
    _flow_row(confirm_db, ts=datetime(2026, 9, 2, 10, 10), d=d, tenor="far",
             n_expiries=2, call_vol=10, put_vol=5, call_notional=900.0,
             put_notional=450.0, call_buy_share=0.5, put_buy_share=0.5, spot=700.0)
    hit = {"dir": "DOWN", "spot": 699.0, "at": datetime(2026, 9, 2, 10, 11)}
    R.flow_record_at_fire(d, hit)

    db = confirm_db()
    row = db.query(R.RiskConfirmFlowAtFire).filter(
        R.RiskConfirmFlowAtFire.tenor == "far").one()
    db.close()
    assert row.call_vol_d is None
    assert row.put_vol_d is None
    assert row.call_vol == 10   # cumulative still reported
