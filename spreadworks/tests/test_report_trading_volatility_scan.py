"""TradingVolatility cross-ticker scan collector for the morning/intraday report.

Response shapes below are copied from real live TradingVolatility v2 API calls made
2026-10-13 (rank_top_setups, rank_income_setups, get_market_structure, get_series) --
not guessed, to avoid the same silent-shape-mismatch bug found in futures_context's
narrative builder (PR #3289).
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import report_trading_volatility_scan as scan

UTC = timezone.utc


def _resp(payload):
    return SimpleNamespace(status_code=200, json=lambda: payload, text="")


TOP_SETUPS_LONG = {"data": {"items": [
    {"ticker": "AUPH", "price": 16.44, "opportunity_score": 7.3, "opportunity_tier": "moderate",
     "regime_label": "trending_low_vol", "iv_rank": 22.6,
     "trade_setup": {"structures": ["long_equity", "long_calls"], "entry_trigger": "Buy pullbacks toward the 20-day average while it holds",
                      "stop_description": "A close back below the last swing low / support",
                      "target_description": "The next resistance band, or 2:1 reward-to-risk",
                      "caution_flags": []}},
]}}

TOP_SETUPS_SHORT = {"data": {"items": [
    {"ticker": "CANE", "price": 12.35, "opportunity_score": 6.7, "opportunity_tier": "moderate",
     "regime_label": "trending_low_vol", "iv_rank": 27.6,
     "trade_setup": {"structures": ["long_puts"], "entry_trigger": "As momentum stalls and the stretch starts to fade",
                      "stop_description": "A fresh extreme beyond the current stretch",
                      "target_description": "A drift back toward the 20-day average",
                      "caution_flags": ["conflicting_alignment", "direction_bias_conflict"]}},
]}}

INCOME_SETUPS = {"data": {"items": [
    {"ticker": "GME", "strategy": "csp", "strike": 21.5, "dte": 30, "premium": 0.44,
     "annualized_yield": 0.249, "breakeven": 21.06, "assignment_or_cap_price": 21.06,
     "income_score": 9, "income_tier": "high", "iv_rank": 100, "earnings_date": None},
]}}

MARKET_STRUCTURE_SPY = {"data": {
    "bias": "neutral", "headline": "Price is sitting near the gamma flip",
    "key_levels": {"spot": 778.38, "gamma_flip": 777.88},
    "supporting_factors": {"pcr_oi": 1.36, "pcr_volume": 1.25,
                            "expected_move_pct_1d": 0.7638, "expected_move_pct_1w": 1.708},
}}

SERIES_SPY = {"data": {"points": [
    {"date": "2026-09-14", "iv_rank": 16.2, "pcr_oi": 1.78, "pcr_volume": 1.31,
     "put_call_ratio_oi_30day_change": 0.53, "put_call_ratio_oi_60day_change": 0.31},
    {"date": "2026-10-13", "iv_rank": 9.1, "pcr_oi": 1.36, "pcr_volume": 1.25,
     "put_call_ratio_oi_30day_change": -0.43, "put_call_ratio_oi_60day_change": 0.21},
]}}

EMPTY_MARKET_STRUCTURE = {"data": {"bias": "neutral", "supporting_factors": {}}}
EMPTY_SERIES = {"data": {"points": []}}


class OrderedFakeClient:
    """Routes by URL + the recommended_direction param (long/short share one /top-setups path)."""
    def __init__(self):
        self.calls = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(url)
        params = params or {}
        if url.endswith("/top-setups"):
            return _resp(TOP_SETUPS_LONG if params.get("recommended_direction") == "long" else TOP_SETUPS_SHORT)
        if url.endswith("/income-setups"):
            return _resp(INCOME_SETUPS)
        if url.endswith("/market-structure"):
            return _resp(MARKET_STRUCTURE_SPY if "/SPY/" in url else EMPTY_MARKET_STRUCTURE)
        if url.endswith("/series"):
            return _resp(SERIES_SPY if "/SPY/" in url else EMPTY_SERIES)
        raise AssertionError(f"Unexpected call: {url}")


@pytest.mark.asyncio
async def test_missing_credentials_returns_reason_without_network(monkeypatch):
    monkeypatch.delenv("TRADING_VOLATILITY_API_TOKEN", raising=False)
    monkeypatch.delenv("TRADING_VOLATILITY_API_KEY", raising=False)
    client = OrderedFakeClient()
    result = await scan.collect_trade_volatility_scan(client, datetime(2026, 10, 13, 14, 0, tzinfo=UTC))
    assert result == {"reason": "TradingVolatility credentials are not configured"}
    assert client.calls == []


@pytest.mark.asyncio
async def test_full_scan_normalizes_real_response_shapes(monkeypatch):
    monkeypatch.setenv("TRADING_VOLATILITY_API_TOKEN", "test-token")
    client = OrderedFakeClient()
    now = datetime(2026, 10, 13, 14, 0, tzinfo=UTC)
    result = await scan.collect_trade_volatility_scan(client, now)

    assert result["source_timestamp"] == now.isoformat()
    longs = result["top_long_setups"]
    assert longs[0]["ticker"] == "AUPH"
    assert longs[0]["structures"] == ["long_equity", "long_calls"]
    assert longs[0]["entry_trigger"] == "Buy pullbacks toward the 20-day average while it holds"

    shorts = result["top_short_setups"]
    assert shorts[0]["ticker"] == "CANE"
    assert shorts[0]["caution_flags"] == ["conflicting_alignment", "direction_bias_conflict"]

    income = result["income_setups"]
    assert income[0] == {"ticker": "GME", "strategy": "csp", "strike": 21.5, "dte": 30,
                          "premium": 0.44, "annualized_yield": 0.249, "breakeven": 21.06,
                          "assignment_or_cap_price": 21.06, "income_score": 9,
                          "income_tier": "high", "earnings_date": None}

    pcr = result["put_call_ratio"]["SPY"]
    assert pcr == {"pcr_oi": 1.36, "pcr_volume": 1.25, "change_30day": -0.43, "change_60day": 0.21}
    assert "VIX" not in result["put_call_ratio"] or result["put_call_ratio"].get("VIX") is None

    trend = result["expected_move_trend"]["SPY"]
    assert trend["expected_move_pct_1d"] == 0.7638
    assert trend["iv_rank_now"] == 9.1 and trend["iv_rank_30d_ago"] == 16.2
    assert trend["trend"] == "collapsing"  # 9.1 - 16.2 = -7.1, below the -5 threshold


@pytest.mark.asyncio
async def test_partial_vendor_failure_degrades_gracefully_not_crash(monkeypatch):
    """One leg failing (e.g. income-setups 500s) must not take down the whole scan -- same
    isolated-collector-failure discipline as every other producer in this report."""
    monkeypatch.setenv("TRADING_VOLATILITY_API_TOKEN", "test-token")

    class FlakyClient(OrderedFakeClient):
        async def get(self, url, params=None, headers=None):
            if url.endswith("/income-setups"):
                return SimpleNamespace(status_code=500, text="upstream error")
            return await super().get(url, params=params, headers=headers)

    client = FlakyClient()
    result = await scan.collect_trade_volatility_scan(client, datetime(2026, 10, 13, 14, 0, tzinfo=UTC))
    assert result["income_setups"] is None
    assert result["top_long_setups"][0]["ticker"] == "AUPH"  # unaffected sibling call still succeeds


@pytest.mark.asyncio
async def test_total_vendor_failure_returns_reason_not_fabricated_data(monkeypatch):
    monkeypatch.setenv("TRADING_VOLATILITY_API_TOKEN", "test-token")

    class DeadClient:
        calls = []
        async def get(self, *a, **k):
            return SimpleNamespace(status_code=500, text="down")

    result = await scan.collect_trade_volatility_scan(DeadClient(), datetime(2026, 10, 13, 14, 0, tzinfo=UTC))
    assert result == {"reason": "TradingVolatility scan returned no usable data"}


def test_normalize_setup_rejects_missing_ticker():
    assert scan._normalize_setup({"opportunity_score": 5}) is None
    assert scan._normalize_setup("not a dict") is None


def test_normalize_income_rejects_missing_ticker():
    assert scan._normalize_income({"strategy": "csp"}) is None
