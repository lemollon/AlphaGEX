"""Trading Volatility cross-ticker scan for the morning/intraday report.

Leron, 2026-10-13: wants the report to answer "which stocks have the best
opportunity to go long/short", "what are the strikes and expirations",
"what is the put/call ratio and does it support the read", and "is the
expected move widening or collapsing". TradingVolatility's v2 API already
computes all of this (deterministic, versioned, third-party) -- this module
calls it directly and normalizes the response into report fields. Nothing
here is invented: every field is TradingVolatility's own output, clearly
sourced, same disclosure discipline as every other collector in this report.

Deliberately independent of trading_volatility_context.py's module-level
_CACHE / rate-limit-retry state, which belongs to the live qqq_retest_watch
alert loop -- report generation must never contend with that watcher's
call budget or inherit its cooldown.
"""
from __future__ import annotations

import asyncio
from datetime import timezone

from .trading_volatility_context import _get, _data, _token

UTC = timezone.utc
SCAN_SYMBOLS = ("SPY", "QQQ", "IWM", "VIX")


def _normalize_setup(item):
    if not isinstance(item, dict):
        return None
    ticker = item.get("ticker")
    if not ticker:
        return None
    setup = item.get("trade_setup") if isinstance(item.get("trade_setup"), dict) else {}
    structures = setup.get("structures")
    structures = structures if isinstance(structures, list) else ([structures] if structures else [])
    caution_flags = setup.get("caution_flags")
    caution_flags = caution_flags if isinstance(caution_flags, list) else ([caution_flags] if caution_flags else [])
    return {
        "ticker": str(ticker).upper(),
        "price": item.get("price"),
        "opportunity_score": item.get("opportunity_score"),
        "opportunity_tier": item.get("opportunity_tier"),
        "regime_label": item.get("regime_label"),
        "trade_bias": item.get("trade_bias"),
        "structures": structures,
        "entry_trigger": setup.get("entry_trigger"),
        "stop_description": setup.get("stop_description"),
        "target_description": setup.get("target_description"),
        "caution_flags": caution_flags,
        "iv_rank": item.get("iv_rank"),
    }


def _normalize_income(item):
    if not isinstance(item, dict):
        return None
    ticker = item.get("ticker")
    if not ticker:
        return None
    return {
        "ticker": str(ticker).upper(),
        "strategy": item.get("strategy"),
        "strike": item.get("strike"),
        "dte": item.get("dte"),
        "premium": item.get("premium"),
        "annualized_yield": item.get("annualized_yield"),
        "breakeven": item.get("breakeven"),
        "assignment_or_cap_price": item.get("assignment_or_cap_price"),
        "income_score": item.get("income_score"),
        "income_tier": item.get("income_tier"),
        "earnings_date": item.get("earnings_date"),
    }


async def _top_setups(client, direction, limit):
    payload = await _get(client, "/top-setups", {"recommended_direction": direction, "limit": limit, "min_score": 0})
    items = _data(payload).get("items")
    items = items if isinstance(items, list) else []
    out = [_normalize_setup(i) for i in items]
    return [o for o in out if o]


async def _market_structure(client, symbol):
    payload = await _get(client, f"/tickers/{symbol}/market-structure", {})
    return _data(payload)


async def _series(client, symbol, window="30d"):
    payload = await _get(client, f"/tickers/{symbol}/series",
                          {"metrics": "iv_rank,pcr_oi,pcr_volume,put_call_ratio_oi_30day_change,put_call_ratio_oi_60day_change",
                           "window": window})
    points = _data(payload).get("points")
    return points if isinstance(points, list) else []


async def collect_trade_volatility_scan(client, now):
    """Returns a flat dict of raw (unwrapped) values for the five new report fields, or
    {'reason': ...} on total failure -- same shape convention as collect_macro/collect_breadth,
    so full_options_report.py wraps each with observation() the same way."""
    if not _token():
        return {"reason": "TradingVolatility credentials are not configured"}

    async def safe(coro):
        try:
            return await coro, None
        except Exception as exc:  # noqa: BLE001
            return None, type(exc).__name__

    try:
        (long_setups, long_err), (short_setups, short_err), (income_payload, income_err) = await asyncio.gather(
            safe(_top_setups(client, "long", 8)),
            safe(_top_setups(client, "short", 8)),
            safe(_get(client, "/income-setups", {"limit": 10})),
        )
    except Exception as exc:  # noqa: BLE001
        return {"reason": "TradingVolatility scan failed: " + type(exc).__name__}

    income_items = []
    if income_payload is not None:
        raw = _data(income_payload).get("items")
        raw = raw if isinstance(raw, list) else []
        income_items = [o for o in (_normalize_income(i) for i in raw) if o]

    structures = {}
    series_points = {}
    for sym in SCAN_SYMBOLS:
        ms_result, ms_err = await safe(_market_structure(client, sym))
        structures[sym] = ms_result if isinstance(ms_result, dict) else None
        sr_result, sr_err = await safe(_series(client, sym))
        series_points[sym] = sr_result or []

    put_call_ratio = {}
    expected_move_trend = {}
    for sym in SCAN_SYMBOLS:
        ms_row = structures.get(sym) or {}
        factors = ms_row.get("supporting_factors") or {}
        points = series_points.get(sym) or []
        pcr_oi = factors.get("pcr_oi")
        pcr_volume = factors.get("pcr_volume")
        change_30d = points[-1].get("put_call_ratio_oi_30day_change") if points else None
        change_60d = points[-1].get("put_call_ratio_oi_60day_change") if points else None
        if pcr_oi is not None or pcr_volume is not None or change_30d is not None:
            put_call_ratio[sym] = {"pcr_oi": pcr_oi, "pcr_volume": pcr_volume,
                                    "change_30day": change_30d, "change_60day": change_60d}

        em_1d = factors.get("expected_move_pct_1d")
        em_1w = factors.get("expected_move_pct_1w")
        iv_rank_now = points[-1].get("iv_rank") if points else None
        iv_rank_then = points[0].get("iv_rank") if len(points) > 1 else None
        trend = None
        if isinstance(iv_rank_now, (int, float)) and isinstance(iv_rank_then, (int, float)):
            delta = iv_rank_now - iv_rank_then
            trend = "widening" if delta > 5 else "collapsing" if delta < -5 else "flat"
        if em_1d is not None or em_1w is not None or trend is not None:
            expected_move_trend[sym] = {"expected_move_pct_1d": em_1d, "expected_move_pct_1w": em_1w,
                                         "iv_rank_now": iv_rank_now, "iv_rank_30d_ago": iv_rank_then, "trend": trend}

    if not (long_setups or short_setups or income_items or put_call_ratio or expected_move_trend):
        return {"reason": "TradingVolatility scan returned no usable data"}

    return {
        "top_long_setups": long_setups or None,
        "top_short_setups": short_setups or None,
        "income_setups": income_items or None,
        "put_call_ratio": put_call_ratio or None,
        "expected_move_trend": expected_move_trend or None,
        "source_timestamp": now.astimezone(UTC).isoformat(),
    }
