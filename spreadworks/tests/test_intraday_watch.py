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


def _raw_setup(symbol="AMD", strategy="call_debit_spread", level=100, setup_id=None):
    value = {
        "symbol": symbol, "strategy": strategy, "thesis": "bullish",
        "entry": {"type": "breakout_hold", "breakout_level": level},
        "invalidation": {"type": "close_below", "level": level - 1},
    }
    if setup_id:
        value["setup_id"] = setup_id
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


def test_opening_range_hold_requires_both_side_tests_and_in_range_closes():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 100, "range_high": 102},
        strategy="double_calendar", thesis="neutral",
    )
    bars = _bars(
        [100.4, 101.7, 101.0, 101.2],
        lows=[99.9, 101.2, 100.7, 100.8],
        highs=[100.8, 102.1, 101.4, 101.5],
    )
    result = _evaluate(setup, bars, price=101.1)
    assert result.state == "ENTRY_READY"
    assert "both sides" in result.reason


def test_opening_range_hold_is_near_only_inside_range_until_both_sides_test():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 100, "range_high": 102},
        strategy="iron_condor", thesis="neutral",
    )
    bars = _bars([100.4, 100.8], lows=[99.9, 100.4], highs=[101.0, 101.2])
    assert _evaluate(setup, bars, price=101).state == "NEAR_TRIGGER"
    assert _evaluate(setup, bars, price=102.01).state == "WAIT"


def test_opening_range_hold_accepts_exact_boundaries():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 100, "range_high": 102},
        strategy="double_calendar", thesis="neutral",
    )
    bars = _bars([100, 102], lows=[100, 101], highs=[101, 102])
    assert _evaluate(setup, bars, price=102).state == "ENTRY_READY"


def test_opening_range_hold_rejects_stale_quote_and_completed_bar():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 100, "range_high": 102},
        strategy="iron_condor", thesis="neutral",
    )
    bars = _bars([100, 102], lows=[100, 101], highs=[101, 102])
    assert _evaluate(setup, bars, price=101, quote_at=NOW - timedelta(seconds=91)).state == "DATA_UNAVAILABLE"
    old = [
        MarketBar(NOW - timedelta(minutes=4), 100, 101, 100, 100.5),
        MarketBar(NOW - timedelta(minutes=3), 101, 102, 101, 101.5),
    ]
    assert _evaluate(setup, old, price=101).state == "DATA_UNAVAILABLE"


def test_opening_range_hold_validation_is_neutral_and_bounded():
    valid = _raw_setup("BX", strategy="double_calendar")
    valid.update(
        thesis="neutral",
        entry={"type": "opening_range_hold", "range_low": 50,
               "range_high": 52, "confirmation_bars": 1},
    )
    assert watch.validate_setup(valid, date(2026, 9, 18))["entry"]["confirmation_bars"] == 1
    invalid_range = dict(valid, entry={"type": "opening_range_hold", "range_low": 52, "range_high": 52})
    with pytest.raises(HTTPException, match="range_low must be below"):
        watch.validate_setup(invalid_range, date(2026, 9, 18))
    directional = dict(valid, thesis="bullish")
    with pytest.raises(HTTPException, match="requires a neutral"):
        watch.validate_setup(directional, date(2026, 9, 18))
    too_many = dict(valid, entry={"type": "opening_range_hold", "range_low": 50,
                                  "range_high": 52, "confirmation_bars": 11})
    with pytest.raises(HTTPException, match="confirmation_bars"):
        watch.validate_setup(too_many, date(2026, 9, 18))


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


def test_fetch_symbol_market_uses_fresh_bbo_midpoint_when_last_is_stale(monkeypatch):
    last_at = int((NOW - timedelta(seconds=120)).timestamp() * 1000)
    bid_at = int((NOW - timedelta(seconds=20)).timestamp() * 1000)
    ask_at = int((NOW - timedelta(seconds=10)).timestamp() * 1000)

    async def fake_get(_app, path, _params):
        if path.endswith("quotes"):
            return {"quotes": {"quote": {
                "symbol": "QQQ", "last": 100, "trade_date": last_at,
                "bid": 101, "ask": 101.2, "bid_date": bid_at, "ask_date": ask_at,
            }}}
        return {"series": {"data": []}}

    monkeypatch.setattr(watch, "_tradier_get", fake_get)
    market = asyncio.run(watch.fetch_symbol_market(object(), "QQQ", NOW))
    assert market["price"] == pytest.approx(101.1)
    assert market["price_basis"] == "bid/ask midpoint"
    assert market["quote_timestamp"] == NOW - timedelta(seconds=20)
    assert market["fresh"] is True


def test_fetch_symbol_market_uses_fresh_bbo_midpoint_when_last_is_missing(monkeypatch):
    bid_at = int((NOW - timedelta(seconds=15)).timestamp() * 1000)
    ask_at = int((NOW - timedelta(seconds=5)).timestamp() * 1000)

    async def fake_get(_app, path, _params):
        if path.endswith("quotes"):
            return {"quotes": {"quote": {
                "symbol": "XSP", "last": None, "trade_date": None,
                "bid": 700, "ask": 700.4, "bid_date": bid_at, "ask_date": ask_at,
            }}}
        return {"series": {"data": []}}

    monkeypatch.setattr(watch, "_tradier_get", fake_get)
    market = asyncio.run(watch.fetch_symbol_market(object(), "XSP", NOW))
    assert market["price"] == pytest.approx(700.2)
    assert market["price_basis"] == "bid/ask midpoint"
    assert market["quote_timestamp"] == NOW - timedelta(seconds=15)


def test_fetch_symbol_market_preserves_stale_last_when_bbo_is_also_stale(monkeypatch):
    last_at = int((NOW - timedelta(seconds=120)).timestamp() * 1000)
    bid_at = int((NOW - timedelta(seconds=110)).timestamp() * 1000)
    ask_at = int((NOW - timedelta(seconds=100)).timestamp() * 1000)
    bar_at = int((NOW - timedelta(minutes=1, seconds=30)).timestamp())

    async def fake_get(_app, path, _params):
        if path.endswith("quotes"):
            return {"quotes": {"quote": {
                "symbol": "QQQ", "last": 100, "trade_date": last_at,
                "bid": 101, "ask": 101.2, "bid_date": bid_at, "ask_date": ask_at,
            }}}
        return {"series": {"data": [{
            "timestamp": bar_at, "open": 100, "high": 101,
            "low": 99.9, "close": 100.5, "volume": 1000,
        }]}}

    monkeypatch.setattr(watch, "_tradier_get", fake_get)
    market = asyncio.run(watch.fetch_symbol_market(object(), "QQQ", NOW))
    assert market["price"] == 100
    assert market["price_basis"] == "last trade"
    assert market["fresh"] is False
    result = evaluate_setup(
        _setup({"type": "breakout_hold", "breakout_level": 99}),
        market["bars"], NOW, quote_timestamp=market["quote_timestamp"],
        quote_price=market["price"],
    )
    assert result.state == "DATA_UNAVAILABLE"
    assert "quote is stale" in result.reason


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


def test_bx_like_double_calendar_is_liquidity_blocked():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 124, "range_high": 124.9},
        symbol="BX", strategy="double_calendar", thesis="neutral", current_price=124.46,
        support_levels=[124], resistance_levels=[126],
    )
    front = [
        _contract(124, "P", -.4505, 2.23, 2.47, oi=541, volume=2021),
        _contract(126, "C", .4238, 1.72, 1.97, oi=16, volume=14),
    ]
    back = [
        _contract(124, "P", -.4539, 3.10, 3.65, oi=60, volume=1),
        _contract(126, "C", .4597, 2.85, 3.05, oi=10, volume=0),
    ]
    result = watch.select_calendar_structure(
        "double_calendar", front, back, setup, "2026-09-25", "2026-10-02",
    )
    assert result["liquidity_status"] == "BLOCKED"
    assert result["natural_debit"] == 2.75
    assert result["composite_midpoint_debit"] == 2.13
    assert result["natural_midpoint_gap_ratio"] == pytest.approx(.29108, abs=1e-6)
    assert "max_risk" not in result
    assert any("spread 16.3% exceeds 15.0%" in item for item in result["failed_checks"])
    assert any("activity OI 10 / volume 0" in item for item in result["failed_checks"])
    assert any("gap 29.1% exceeds 12.5%" in item for item in result["failed_checks"])


def test_calendar_prefers_liquid_alternative_inside_delta_band():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 124, "range_high": 126},
        strategy="double_calendar", thesis="neutral", current_price=125,
        support_levels=[124], resistance_levels=[126],
    )
    front = [
        _contract(124, "P", -.45, 2.23, 2.47, oi=541, volume=2021),
        _contract(123, "P", -.38, 2.00, 2.10, oi=100, volume=20),
        _contract(126, "C", .42, 1.72, 1.97, oi=16, volume=14),
        _contract(127, "C", .38, 1.50, 1.60, oi=100, volume=20),
    ]
    back = [
        _contract(124, "P", -.45, 3.10, 3.65, oi=60, volume=1),
        _contract(123, "P", -.40, 3.00, 3.10, oi=100, volume=20),
        _contract(126, "C", .46, 2.85, 3.05, oi=10, volume=0),
        _contract(127, "C", .40, 2.50, 2.60, oi=100, volume=20),
    ]
    result = watch.select_calendar_structure(
        "double_calendar", front, back, setup, "2026-09-25", "2026-10-02",
    )
    assert result["liquidity_status"] == "PASS"
    assert [leg["strike"] for leg in result["legs"]] == [123, 123, 127, 127]
    assert result["natural_midpoint_gap_ratio"] == pytest.approx(.10)


def test_calendar_liquidity_exact_boundaries_are_accepted():
    setup = _setup(
        {"type": "breakout_hold", "breakout_level": 100},
        strategy="calendar", thesis="bullish", current_price=100,
    )
    front = [_contract(100, "C", .40, .925, 1.075, oi=50, volume=0)]
    back = [_contract(100, "C", .40, 2.125, 2.275, oi=50, volume=0)]
    result = watch.select_calendar_structure(
        "calendar", front, back, setup, "2026-09-25", "2026-10-02",
    )
    assert result["liquidity_status"] == "PASS"
    assert result["legs"][0]["relative_spread"] == pytest.approx(.15)
    assert result["natural_midpoint_gap_ratio"] == pytest.approx(.125)


def test_calendar_missing_open_interest_and_volume_is_blocked():
    setup = _setup(
        {"type": "breakout_hold", "breakout_level": 100},
        strategy="calendar", thesis="bullish", current_price=100,
    )
    front = [_contract(100, "C", .40, 1.00, 1.05, oi=0, volume=0)]
    back = [_contract(100, "C", .40, 2.00, 2.05, oi=0, volume=0)]
    result = watch.select_calendar_structure(
        "calendar", front, back, setup, "2026-09-25", "2026-10-02",
    )
    assert result["liquidity_status"] == "BLOCKED"
    assert len([item for item in result["failed_checks"] if "activity OI 0 / volume 0" in item]) == 2


def test_calendar_liquidity_overrides_are_validated_and_preserved():
    raw = {
        "symbol": "BX", "strategy": "double_calendar", "thesis": "neutral",
        "entry": {"type": "opening_range_hold", "range_low": 124, "range_high": 125},
        "invalidation": {"type": "none"},
        "maximum_relative_leg_spread": .20,
        "maximum_natural_midpoint_gap_ratio": .25,
        "minimum_calendar_open_interest": 25,
        "minimum_calendar_volume": 5,
    }
    validated = watch.validate_setup(raw, date(2026, 9, 18))
    assert validated["maximum_relative_leg_spread"] == .20
    assert validated["maximum_natural_midpoint_gap_ratio"] == .25
    assert validated["minimum_calendar_open_interest"] == 25
    assert validated["minimum_calendar_volume"] == 5
    with pytest.raises(HTTPException, match="maximum_relative_leg_spread"):
        watch.validate_setup({**raw, "maximum_relative_leg_spread": 0}, date(2026, 9, 18))
    with pytest.raises(HTTPException, match="minimum_calendar_volume"):
        watch.validate_setup({**raw, "minimum_calendar_volume": 1.5}, date(2026, 9, 18))


def test_blocked_calendar_converts_entry_ready_to_no_trade_state():
    blocked = {
        "liquidity_status": "BLOCKED",
        "failed_checks": ["natural-to-midpoint debit gap 29.1% exceeds 12.5%"],
    }
    result = watch.apply_option_liquidity_state(
        watch.RuleResult("ENTRY_READY", "underlying confirmed", ("underlying confirmed",)),
        blocked,
    )
    assert result.state == "LIQUIDITY_BLOCKED"
    assert "no trade" in result.reason
    assert result.evidence == ("underlying confirmed",)
    passing = watch.apply_option_liquidity_state(
        watch.RuleResult("ENTRY_READY", "underlying confirmed"), {"liquidity_status": "PASS"},
    )
    assert passing.state == "ENTRY_READY"


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


@pytest.mark.parametrize(("symbols", "raw_setups", "message"), [
    (["AMD"], [_raw_setup("NVDA")], "selected symbols without actionable setups"),
    (["AMD"], [_raw_setup("QQQ")], "selected symbols without actionable setups"),
    ([], [_raw_setup("AMD")], "outside selected watchlist"),
])
def test_morning_plan_rejects_watchlist_setup_parity_mismatches(symbols, raw_setups, message):
    setups = [watch.validate_setup(item, date(2026, 9, 18)) for item in raw_setups]
    with pytest.raises(HTTPException, match=message):
        watch.validate_plan_parity(symbols, setups)


def test_watch_only_and_no_trade_are_not_actionable_setups():
    with pytest.raises(HTTPException, match="not actionable"):
        watch.validate_setup(_raw_setup(strategy="Watch Only"), date(2026, 9, 18))
    raw = _raw_setup()
    raw["recommendation"] = "No Trade"
    with pytest.raises(HTTPException, match="not actionable"):
        watch.validate_setup(raw, date(2026, 9, 18))


def test_exact_plan_parity_accepts_core_and_multiple_setups_per_selected_ticker(sqlite_store):
    trading_date = date(2026, 9, 18)
    setups = [
        watch.validate_setup(_raw_setup("AMD", level=100, setup_id="amd-breakout"), trading_date),
        watch.validate_setup(_raw_setup("AMD", strategy="put_credit_spread", level=99, setup_id="amd-credit"), trading_date),
        watch.validate_setup(_raw_setup("QQQ", level=718, setup_id="qqq-core"), trading_date),
    ]
    response = watch.store_morning_plan_atomic(
        trading_date, ["AMD"], setups,
        {"trading_date": trading_date.isoformat(), "symbols": ["AMD"], "setups": setups},
        ingested_at=NOW,
    )
    assert response["registered_symbol_count"] == 1
    assert response["registered_setup_count"] == 3
    assert response["registered_total_symbol_count"] == 5
    assert response["parity"]["valid"] is True
    assert response["plan_hash"] == watch.plan_hash(trading_date, ["AMD"], list(reversed(setups)))


def test_atomic_plan_rolls_back_all_three_surfaces_on_commit_failure(sqlite_store, monkeypatch):
    trading_date = date(2026, 9, 18)
    setup = watch.validate_setup(_raw_setup("AMD"), trading_date)
    real_factory = sqlite_store

    class FailingSession:
        def __init__(self):
            self._session = real_factory()

        def __getattr__(self, name):
            return getattr(self._session, name)

        def commit(self):
            raise RuntimeError("forced commit failure")

    monkeypatch.setattr(watch, "SessionLocal", FailingSession)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        watch.store_morning_plan_atomic(
            trading_date, ["AMD"], [setup],
            {"trading_date": trading_date.isoformat(), "symbols": ["AMD"], "setups": [setup]},
            ingested_at=NOW,
        )
    db = real_factory()
    try:
        assert db.get(IntradayTradePlan, trading_date) is None
        assert db.get(IntradaySelectedWatchlist, trading_date) is None
        assert db.query(IntradaySetup).count() == 0
    finally:
        db.close()


def test_status_exposes_plan_hash_ingestion_and_parity(sqlite_store):
    trading_date = date(2026, 9, 18)
    setup = watch.validate_setup(_raw_setup("AMD"), trading_date)
    stored = watch.store_morning_plan_atomic(
        trading_date, ["AMD"], [setup],
        {"trading_date": trading_date.isoformat(), "symbols": ["AMD"], "setups": [setup]},
        ingested_at=NOW,
    )
    result = asyncio.run(watch.run_intraday_cycle(
        SimpleNamespace(state=SimpleNamespace(http=None)), now=NOW
    ))
    assert result["plan_hash"] == stored["plan_hash"]
    assert result["plan_ingestion_timestamp"] == NOW.isoformat()
    assert result["plan_parity"]["valid"] is True


def test_plan_endpoint_requires_symbols_and_setups(monkeypatch):
    class Request:
        async def json(self):
            return {"trading_date": "2026-09-18", "symbols": ["AMD"]}

    monkeypatch.setenv("INTRADAY_WATCH_API_TOKEN", "configured-token")
    with pytest.raises(HTTPException, match="requires both symbols and setups"):
        asyncio.run(watch.post_plan(
            Request(), x_intraday_watch_token="configured-token", authorization=None
        ))


def test_alert_embed_is_decision_first_human_readable_and_has_no_raw_json():
    setup = _setup(
        {"type": "breakout_retest", "breakout_level": 718},
        invalidation={"type": "close_below", "level": 717},
        profit_taking_framework=None, main_risks=None,
    )
    market = {
        "price": 719.25, "price_basis": "bid/ask midpoint",
        "source": "Tradier production consolidated feed", "session": "regular",
        "exchange_timestamp": (NOW - timedelta(seconds=12)).isoformat(),
        "retrieval_timestamp": NOW.isoformat(), "age_seconds": 12.0,
    }
    stamp = (NOW - timedelta(seconds=8)).isoformat()
    option_selection = {
        "source": "Tradier production option chain", "expiration": "2026-09-25",
        "natural_debit": 1.25, "width": 5, "max_risk": 125,
        "legs": [{
            "action": "buy", "right": "C", "strike": 720, "bid": 3.1,
            "ask": 3.2, "delta": .57, "gamma": .04, "theta": -.08,
            "vega": .11, "iv": .24, "exchange_timestamp": stamp,
            "retrieval_timestamp": NOW.isoformat(), "age_seconds": 8,
        }, {
            "action": "sell", "right": "C", "strike": 725, "bid": 1.95,
            "ask": 2.05, "delta": .33, "gamma": .03, "theta": -.05,
            "vega": .09, "iv": .23, "exchange_timestamp": stamp,
            "retrieval_timestamp": NOW.isoformat(), "age_seconds": 8,
        }],
    }
    embed = watch.build_alert_embed(
        setup, "WAIT", watch.RuleResult("ENTRY_READY", "Two completed bars confirmed the retest."),
        market, option_selection, None, NOW,
    )
    values = "\n".join(field["value"] for field in embed["fields"])
    assert embed["title"] == "ENTRY READY — QQQ CALL DEBIT SPREAD"
    assert embed["fields"][0]["name"] == "Action"
    assert "Break above $718, retest it" in values
    assert "completed 1-minute close below $717" in values
    assert "BUY C $720" in values and "SELL C $725" in values
    assert "bid/ask 3.10/3.20" in values and "Δ 0.570" in values
    assert "Natural debit $1.25" in values and "max risk $125.00" in values
    assert "2026-09-18 10:34:18 AM ET" in values
    assert "NOT DEFINED — plan did not provide a profit target" in values
    assert "NOT DEFINED — plan did not provide the main setup risk" in values
    assert "{" not in values and "}" not in values
    assert embed["footer"]["text"].endswith("no order routing")
    rendered_framework = watch._defined_or_warning(
        {"take_profit": "50% of debit", "scale_out": "first target"},
        "a profit target",
    )
    assert rendered_framework == "take profit: 50% of debit; scale out: first target"
    assert "{" not in rendered_framework


def test_data_unavailable_embed_explicitly_says_no_trade_and_auto_resume():
    setup = _setup({"type": "breakout_hold", "breakout_level": 718})
    market = {
        "price": 717.5, "price_basis": "last trade",
        "source": "Tradier production consolidated feed", "session": "regular",
        "exchange_timestamp": (NOW - timedelta(seconds=121)).isoformat(),
        "retrieval_timestamp": NOW.isoformat(), "age_seconds": 121.0,
    }
    embed = watch.build_alert_embed(
        setup, "NEAR_TRIGGER",
        watch.RuleResult("DATA_UNAVAILABLE", "Underlying quote is stale (121.0s)."),
        market, None, "options not requested", NOW,
    )
    values = "\n".join(field["value"] for field in embed["fields"])
    assert embed["title"] == "NO TRADE — QQQ DATA UNAVAILABLE"
    assert "NO TRADE" in values
    assert "stale (121.0s)" in values
    assert "90 seconds old or less" in values
    assert "Monitoring resumes automatically" in values


def test_liquidity_blocked_embed_is_explicitly_not_executable():
    setup = _setup(
        {"type": "opening_range_hold", "range_low": 124, "range_high": 124.9},
        symbol="BX", strategy="double_calendar", thesis="neutral", current_price=124.46,
        support_levels=[124], resistance_levels=[126],
    )
    selection = watch.select_calendar_structure(
        "double_calendar",
        [_contract(124, "P", -.45, 2.23, 2.47, oi=541, volume=2021),
         _contract(126, "C", .42, 1.72, 1.97, oi=16, volume=14)],
        [_contract(124, "P", -.45, 3.10, 3.65, oi=60, volume=1),
         _contract(126, "C", .46, 2.85, 3.05, oi=10, volume=0)],
        setup, "2026-09-25", "2026-10-02",
    )
    result = watch.apply_option_liquidity_state(
        watch.RuleResult("ENTRY_READY", "underlying confirmed"), selection,
    )
    market = {
        "price": 124.46, "price_basis": "last trade",
        "source": "Tradier production consolidated feed", "session": "regular",
        "exchange_timestamp": (NOW - timedelta(seconds=5)).isoformat(),
        "retrieval_timestamp": NOW.isoformat(), "age_seconds": 5.0,
    }
    embed = watch.build_alert_embed(setup, "ENTRY_READY", result, market, selection, None, NOW)
    names = [field["name"] for field in embed["fields"]]
    values = "\n".join(field["value"] for field in embed["fields"])
    assert embed["title"] == "NO TRADE — BX LIQUIDITY BLOCKED"
    assert "Observed option legs — NOT EXECUTABLE" in names
    assert "Observed pricing — NOT EXECUTABLE" in names
    assert "Defined cost / risk" not in names
    assert "NO TRADE" in values
    assert "natural debit $2.75" in values
    assert "natural-vs-mid gap 29.1%" in values
    assert "max leg spread 15.0%" in values
    assert "session regular" in values
    assert embed["footer"]["text"].endswith("no order routing")


def test_no_order_routing_imports_or_calls_exist():
    source = Path(watch.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    called = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert not any("executor" in name or "broker" in name for name in imported)
    assert not {"place_order", "preview_order", "cancel_order", "modify_order"}.intersection(called)
