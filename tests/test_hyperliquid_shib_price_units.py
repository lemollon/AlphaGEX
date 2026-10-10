"""Regression test for the SHIB-PERP entry/mark unit mismatch.

Hyperliquid quotes SHIB as "kSHIB" - priced per 1000 SHIB, roughly 1000x the
plain per-token spot price CryptoDataProvider (Coinbase) and the AGAPE-SHIB-PERP
trader use everywhere else (stop/target calc, mark-to-market, exits). Before
the fix, HyperliquidPerpProvider.get_market("SHIB") returned the raw kSHIB
quote unconverted, so paper fills built from it (entry_price) landed ~1000x
above the spot price used for mark-to-market and exits.

See: AGAPE-SHIB-PERP paper positions with entry_price ~0.0056 vs
current_shib_price ~5.6e-06 (2026-09-23).
"""

import pytest

from data.hyperliquid_perp_provider import HyperliquidPerpProvider
import data.hyperliquid_perp_provider as hlp
from trading.shared.perp_realism import simulate_selective_reference_fill

# Realistic kSHIB quote on Hyperliquid: priced per 1000 SHIB.
KSHIB_MARK = 0.0056
KSHIB_BID = 0.00559
KSHIB_ASK = 0.00561
# True per-SHIB spot price (Coinbase-style), matching CryptoDataProvider.
SHIB_SPOT_PRICE = 0.0000056


def _fake_post(self, payload):
    if payload.get("type") == "metaAndAssetCtxs":
        meta = {
            "universe": [
                {"name": "kSHIB", "maxLeverage": 20, "marginTableId": None},
            ],
            "marginTables": [],
        }
        ctxs = [{"markPx": str(KSHIB_MARK), "oraclePx": str(KSHIB_MARK), "funding": "0.0001"}]
        return [meta, ctxs]
    if payload.get("type") == "l2Book":
        return {
            "levels": [
                [{"px": str(KSHIB_BID)}],
                [{"px": str(KSHIB_ASK)}],
            ],
            "time": 1,
        }
    raise AssertionError(f"unexpected payload: {payload}")


@pytest.fixture(autouse=True)
def _mock_hyperliquid(monkeypatch):
    monkeypatch.setattr(HyperliquidPerpProvider, "_post", _fake_post)
    hlp._provider = None
    yield
    hlp._provider = None


def test_get_market_converts_kshib_to_per_token_price():
    """kSHIB quotes (per 1000 SHIB) must come back in per-SHIB units."""
    market = HyperliquidPerpProvider().get_market("SHIB")
    assert market is not None
    # Converted price must land in the same order of magnitude as the real
    # per-token spot price, not the raw 1000x kSHIB quote.
    assert market.quote.mark == pytest.approx(KSHIB_MARK / 1000, rel=1e-9)
    assert market.quote.bid == pytest.approx(KSHIB_BID / 1000, rel=1e-9)
    assert market.quote.ask == pytest.approx(KSHIB_ASK / 1000, rel=1e-9)
    assert market.quote.mark < 0.00001, "mark still looks like a raw kSHIB (1000x) price"


def test_shib_perp_entry_price_shares_units_with_mark_price():
    """Entry (paper fill) price must be within 5% of the mark price used
    for the same market data - i.e. same units, not off by a factor of 1000."""
    fill, market, _rules = simulate_selective_reference_fill(
        "SHIB-PERP",
        "long",
        1_000_000.0,
        SHIB_SPOT_PRICE,
        default_leverage=3.0,
        max_leverage=20.0,
        fallback_maintenance_margin_rate=0.01,
        prefer_maker=False,
    )
    assert market is not None
    entry_price = fill.fill_price
    mark_price = market.quote.mark
    assert entry_price == pytest.approx(mark_price, rel=0.05)
    # And the mark price itself must be in the same unit family as the spot
    # price everywhere else in the bot uses for mark-to-market.
    assert mark_price == pytest.approx(SHIB_SPOT_PRICE, rel=0.05)
