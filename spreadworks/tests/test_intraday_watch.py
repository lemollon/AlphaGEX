"""Pure/unit coverage for the alert-only generalized intraday watcher."""
from __future__ import annotations

import ast
import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.intraday_watch as watch
from backend.db import Base
from backend.intraday_watch import MarketBar, evaluate_setup, select_option_structure
from backend.models import (
    IntradayAlertDedup,
    IntradaySelectedWatchlist,
    IntradaySetup,
    IntradayTradePlan,
    IntradayWatchRuntimeStatus,
    QQQWatchRuntimeStatus,
)

UTC = timezone.utc
NOW = datetime(2026, 9, 18, 14, 34, 30, tzinfo=UTC)


def _setup(entry: dict, **overrides):
    value = {
        "setup_id": "qqq-one", "trading_date": "2026-09-18", "symbol": "QQQ",
        "strategy": "call_debit_spread", "thesis": "bullish", "setup_state": "WAIT",
        "entry": {"confirmation_bars": 2, **entry},
        "invalidation": {"type": "close_below", "level": 99},
        "sessions": ["regular"],
    }
    value.update(overrides)
    return value


def _bars(closes, lows=None, highs=None, vwaps=None):
    start = NOW - timedelta(minutes=len(closes), seconds=30)
    rows = []
    for index, close in enumerate(closes):
        rows.append(MarketBar(
            timestamp=start + timedelta(minutes=index), open=close - .1,
            high=(highs or closes)[index], low=(lows or closes)[index], close=close,
            volume=1000, vwap=(vwaps[index] if vwaps else None),
        ))
    return rows


def _evaluate(setup, bars, price=None, quote_at=None, **kwargs):
    return evaluate_setup(setup, bars, NOW, quote_timestamp=quote_at or NOW - timedelta(seconds=10),
                          quote_price=price if price is not None else bars[-1].close, **kwargs)


def test_breakout_hold_requires_completed_confirmation_bars():
    result = _evaluate(_setup({"type": "breakout_hold", "breakout_level": 100}), _bars([99.8, 100.2, 100.3]))
    assert result.state == "ENTRY_READY"


def test_breakout_retest_requires_breakout_then_retest_and_hold():
    bars = _bars([99.8, 100.4, 100.1, 100.2], lows=[99.7, 100.1, 99.95, 100.05])
    result = _evaluate(_setup({"type": "breakout_retest", "breakout_level": 100}), bars)
    assert result.state == "ENTRY_READY"


def test_support_hold_requires_touch_and_completed_holds():
    bars = _bars([101, 100.5, 100.8], lows=[100.9, 99.5, 100.2], highs=[101.1, 100.6, 100.9])
    result = _evaluate(_setup({"type": "support_hold", "support_low": 99, "support_high": 100}), bars)
    assert result.state == "ENTRY_READY"


def test_failed_reclaim_requires_rejection_and_closes_below():
    bars = _bars([100.1, 99.7, 99.6], highs=[100.2, 100.05, 99.8])
    result = _evaluate(_setup({"type": "failed_reclaim", "reclaim_level": 100}), bars)
    assert result.state == "ENTRY_READY"


def test_vwap_reclaim_and_opening_range_rules():
    vwap = _evaluate(_setup({"type": "vwap_reclaim"}), _bars([99.8, 100.2, 100.3], vwaps=[100, 100, 100.1]))
    orb = _evaluate(_setup({"type": "opening_range_breakout", "range_high": 100}), _bars([99.8, 100.2, 100.3]))
    reject = _evaluate(_setup({"type": "opening_range_rejection", "range_low": 100, "range_high": 101}),
                       _bars([100.5, 99.8, 99.7], highs=[100.6, 100.1, 99.9]))
    assert (vwap.state, orb.state, reject.state) == ("ENTRY_READY", "ENTRY_READY", "ENTRY_READY")


def test_relative_strength_confirmation_can_block_otherwise_ready_entry():
    setup = _setup({"type": "breakout_hold", "breakout_level": 100},
                   relative_strength={"minimum_outperformance": .01})
    blocked = _evaluate(setup, _bars([100.2, 100.3]), relative_context={"symbol_return": .01, "reference_return": .02})
    ready = _evaluate(setup, _bars([100.2, 100.3]), relative_context={"symbol_return": .03, "reference_return": .01})
    assert blocked.state != "ENTRY_READY"
    assert ready.state == "ENTRY_READY"


def test_vix_confirmation_is_required_when_specified():
    setup = _setup({"type": "breakout_hold", "breakout_level": 100},
                   confirmation_rule={"inputs": [{"symbol": "VIX", "operator": "below", "value": 20}]})
    blocked = _evaluate(setup, _bars([100.2, 100.3]), confirmation_context={"VIX": 21})
    ready = _evaluate(setup, _bars([100.2, 100.3]), confirmation_context={"VIX": 19})
    unavailable = _evaluate(setup, _bars([100.2, 100.3]), confirmation_context={})
    assert blocked.state != "ENTRY_READY"
    assert ready.state == "ENTRY_READY"
    assert unavailable.state != "ENTRY_READY"


def test_active_or_ready_setup_can_invalidate():
    setup = _setup({"type": "breakout_hold", "breakout_level": 100}, setup_state="ACTIVE",
                   invalidation={"type": "close_below", "level": 99})
    assert _evaluate(setup, _bars([100, 98.5])).state == "INVALIDATED"


def test_stale_quote_and_bar_are_rejected_at_90_seconds():
    setup = _setup({"type": "breakout_hold", "breakout_level": 100})
    stale_quote = _evaluate(setup, _bars([100.2, 100.3]), quote_at=NOW - timedelta(seconds=91))
    old = [MarketBar(NOW - timedelta(minutes=4), 100, 101, 99, 100.2),
           MarketBar(NOW - timedelta(minutes=3), 100, 101, 99, 100.3)]
    stale_bar = _evaluate(setup, old)
    assert stale_quote.state == "DATA_UNAVAILABLE"
    assert stale_bar.state == "DATA_UNAVAILABLE"


def test_prior_day_setup_expires_without_using_levels():
    setup = _setup({"type": "support_hold", "support_low": 99, "support_high": 100})
    setup["trading_date"] = "2026-09-17"
    assert _evaluate(setup, _bars([100, 100])).state == "EXPIRED"


def _contract(strike, right, delta, bid, ask, *, oi=100, volume=20, age=10):
    stamp = int((NOW - timedelta(seconds=age)).timestamp() * 1000)
    return watch.normalize_contract({
        "symbol": f"OPT{strike}", "strike": strike,
        "option_type": "call" if right == "C" else "put",
        "bid": bid, "ask": ask, "bid_date": stamp, "ask_date": stamp,
        "open_interest": oi, "volume": volume,
        "greeks": {"delta": delta, "gamma": .01, "theta": -.02,
                   "vega": .03, "mid_iv": .25,
                   "updated_at": (NOW - timedelta(seconds=age)).isoformat()},
    }, NOW)


def test_stale_greeks_contract_is_rejected():
    assert _contract(100, "C", .55, 2, 2.1, age=91) is None


def test_unknown_option_type_and_missing_greeks_are_rejected():
    stamp = int((NOW - timedelta(seconds=5)).timestamp() * 1000)
    base = {"symbol": "BAD", "strike": 100, "bid": 1, "ask": 1.1,
            "bid_date": stamp, "ask_date": stamp,
            "greeks": {"delta": .5, "gamma": .1, "theta": -.1,
                       "vega": .1, "mid_iv": .2, "updated_at": NOW.isoformat()}}
    assert watch.normalize_contract({**base, "option_type": "unknown"}, NOW) is None
    missing = {**base, "option_type": "call", "greeks": {"delta": .5, "updated_at": NOW.isoformat()}}
    assert watch.normalize_contract(missing, NOW) is None


def test_exact_delta_match_for_long_call():
    chain = [_contract(99, "C", .51, 3, 3.1), _contract(100, "C", .575, 2, 2.1)]
    result = select_option_structure("long_call", chain, _setup({"type": "breakout_hold", "breakout_level": 100}), "2026-09-25")
    assert result["legs"][0]["strike"] == 100


def test_debit_spread_selection_and_economics():
    chain = [_contract(100, "C", .575, 2, 2.1), _contract(105, "C", .325, .8, .9)]
    result = select_option_structure("call_debit_spread", chain, _setup({"type": "breakout_hold", "breakout_level": 100}), "2026-09-25")
    assert [leg["strike"] for leg in result["legs"]] == [100, 105]
    assert result["natural_debit"] == 1.3


def test_put_credit_requires_short_below_support_and_minimum_credit():
    setup = _setup({"type": "support_hold", "support_low": 100, "support_high": 101},
                   strategy="put_credit_spread", support_levels=[100], minimum_credit_to_width=.20)
    chain = [_contract(98, "P", -.20, 1.5, 1.6), _contract(95, "P", -.10, .5, .6)]
    result = select_option_structure("put_credit_spread", chain, setup, "2026-09-25")
    assert result["legs"][0]["strike"] == 98
    assert result["natural_credit"] == .9


def test_call_credit_requires_short_above_resistance():
    setup = _setup({"type": "failed_reclaim", "reclaim_level": 100},
                   strategy="call_credit_spread", resistance_levels=[101])
    chain = [_contract(102, "C", .20, 1.5, 1.6), _contract(105, "C", .10, .5, .6)]
    result = select_option_structure("call_credit_spread", chain, setup, "2026-09-25")
    assert result["legs"][0]["strike"] == 102


def test_calendar_is_strikes_pending_when_only_one_expiration_is_available():
    chain = [_contract(100, "C", .40, 2, 2.1)]
    assert select_option_structure("calendar", chain, _setup({"type": "breakout_hold", "breakout_level": 100}), "2026-09-25") is None


def test_calendar_uses_fresh_same_strike_front_and_back_legs():
    front = [_contract(100, "C", .40, 1.0, 1.1)]
    back = [_contract(100, "C", .42, 1.8, 1.9)]
    result = watch.select_calendar_structure(
        "calendar", front, back,
        _setup({"type": "breakout_hold", "breakout_level": 100}, current_price=100),
        "2026-09-25", "2026-10-02",
    )
    assert [leg["action"] for leg in result["legs"]] == ["sell", "buy"]
    assert result["natural_debit"] == .9


def test_expiration_preference_selects_nearest_band_midpoint():
    setup = {"expiration_preference": "7-14 DTE"}
    values = [date(2026, 9, 25), date(2026, 9, 29), date(2026, 10, 2)]
    assert watch._choose_expiration(values, setup, date(2026, 9, 18)) == date(2026, 9, 29)


def test_xsp_is_never_rewritten_to_spy_in_validation():
    setup = watch.validate_setup({
        "symbol": "XSP", "strategy": "put_credit_spread", "thesis": "bullish",
        "entry": {"type": "support_hold", "support_low": 700, "support_high": 701},
        "invalidation": {"type": "close_below", "level": 699},
    }, date(2026, 9, 18))
    assert setup["symbol"] == "XSP"


@pytest.fixture
def sqlite_store(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine, tables=[
        IntradayTradePlan.__table__, IntradaySelectedWatchlist.__table__,
        IntradaySetup.__table__, IntradayAlertDedup.__table__,
        IntradayWatchRuntimeStatus.__table__, QQQWatchRuntimeStatus.__table__,
    ])
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(watch, "SessionLocal", factory)
    return factory


def test_watchlist_and_setup_state_persist(sqlite_store):
    watch.store_watchlist(date(2026, 9, 18), ["AMD", "NVDA"])
    setup = watch.validate_setup({
        "symbol": "QQQ", "strategy": "call_debit_spread", "thesis": "bullish",
        "entry": {"type": "breakout_hold", "breakout_level": 100},
        "invalidation": {"type": "close_below", "level": 99},
    }, date(2026, 9, 18))
    watch.store_setups(date(2026, 9, 18), [setup])
    db = sqlite_store()
    try:
        assert json.loads(db.get(IntradaySelectedWatchlist, date(2026, 9, 18)).symbols_json) == ["AMD", "NVDA"]
        assert db.get(IntradaySetup, setup["setup_id"]).state == "WAIT"
    finally:
        db.close()


def test_prior_day_rows_are_deactivated(sqlite_store):
    old = _setup({"type": "breakout_hold", "breakout_level": 100})
    old["trading_date"] = "2026-09-17"
    watch.store_setups(date(2026, 9, 17), [old])
    new = dict(old, setup_id="new", trading_date="2026-09-18")
    watch.store_setups(date(2026, 9, 18), [new])
    db = sqlite_store()
    try:
        assert db.get(IntradaySetup, old["setup_id"]).active == 0
    finally:
        db.close()


def test_restart_and_discord_transition_dedup(sqlite_store):
    db = sqlite_store()
    try:
        first = watch.claim_alert(db, "abc", date(2026, 9, 18), "ENTRY_READY", NOW)
        second = watch.claim_alert(db, "abc", date(2026, 9, 18), "ENTRY_READY", NOW + timedelta(seconds=10))
        assert first is not None
        assert second == first
        row = db.get(IntradayAlertDedup, first)
        row.posted_at = NOW
        db.commit()
        assert watch.claim_alert(db, "abc", date(2026, 9, 18), "ENTRY_READY", NOW + timedelta(seconds=20)) is None
    finally:
        db.close()


def test_heartbeat_health_threshold_uses_poll_interval(sqlite_store):
    db = sqlite_store()
    try:
        now = datetime.now(UTC)
        db.add(IntradayWatchRuntimeStatus(watcher_id="intraday-watch",
                 payload_json=json.dumps({"poll_interval_seconds": 60}), heartbeat_at=now))
        db.commit()
    finally:
        db.close()
    assert watch._load_runtime_status()["worker_healthy"] is True


def test_missing_trading_volatility_watchlist_falls_back_to_core_only(sqlite_store):
    result = asyncio.run(watch.run_intraday_cycle(SimpleNamespace(state=SimpleNamespace(http=None)), now=NOW))
    assert result["selected_daily_symbols"] == []
    assert result["core_symbols"] == ["SPY", "QQQ", "XSP", "IWM"]
    assert "no random fallback" in result["errors"][0].lower()


def test_missing_option_data_produces_strikes_pending(monkeypatch):
    async def fake_get(_app, path, _params):
        if path.endswith("expirations"):
            return {"expirations": {"date": ["2026-09-25"]}}
        return {"options": {"option": []}}
    monkeypatch.setattr(watch, "_tradier_get", fake_get)
    selection, reason = asyncio.run(watch.fetch_option_selection(
        object(), _setup({"type": "breakout_hold", "breakout_level": 100}), NOW))
    assert selection is None
    assert reason == "ENTRY TRIGGER HIT — STRIKES PENDING OPTIONS DATA"


@pytest.mark.parametrize("payload", [
    {"trading_date": "bad", "setups": []},
    {"trading_date": "2026-09-18", "setups": [{"symbol": "QQQ;DROP"}]},
    {"trading_date": "2026-09-18", "setups": [{
        "symbol": "QQQ", "strategy": "call_debit_spread", "thesis": "bullish",
        "entry": {"type": "touch", "level": 100},
        "invalidation": {"type": "close_below", "level": 99},
    }]},
])
def test_malformed_setup_payload_is_rejected(payload):
    with pytest.raises(HTTPException):
        watch.validate_setups_payload(payload)


def test_watchlist_rejects_duplicates_and_more_than_eight():
    with pytest.raises(HTTPException):
        watch.validate_watchlist({"trading_date": "2026-09-18", "symbols": ["AMD", "AMD"]})
    with pytest.raises(HTTPException):
        watch.validate_watchlist({"trading_date": "2026-09-18", "symbols": [f"A{i}" for i in range(9)]})


def test_explicit_setup_ids_are_date_bound():
    raw = {"setup_id": "morning-idea", "symbol": "QQQ",
           "strategy": "call_debit_spread", "thesis": "bullish",
           "entry": {"type": "breakout_hold", "breakout_level": 100},
           "invalidation": {"type": "close_below", "level": 99}}
    first = watch.validate_setup(raw, date(2026, 9, 18))["setup_id"]
    second = watch.validate_setup(raw, date(2026, 9, 19))["setup_id"]
    assert first != second


def test_no_order_routing_imports_or_calls_exist():
    source = Path(watch.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    called = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not any("executor" in name or "broker" in name for name in imported)
    assert not {"place_order", "preview_order", "cancel_order", "modify_order"}.intersection(called)
