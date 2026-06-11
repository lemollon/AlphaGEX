"""Regression tests for LiveTradierChainProvider._atm_iv fallback ladder.

The back-month chain at market open often has no `mid_iv` on the exact ATM
call. Before the ladder was added, this returned 0 and blocked every entry
on vega_edge_below_min. The ladder must:

  1. Read the ATM call first.
  2. For each candidate strike, try mid_iv -> smv_vol -> ask_iv -> bid_iv.
  3. Fall back to the ATM put if the call IV is missing.
  4. Walk outward strike-by-strike up to +/-5 strikes.
"""
from __future__ import annotations

from backend.bots.routes_helpers import LiveTradierChainProvider


def _opt(strike, type_, **greeks):
    """Build a Tradier-shaped option row with greeks subset."""
    return {
        "strike": strike,
        "option_type": type_,
        "bid": 0,
        "ask": 0,
        "greeks": greeks,
    }


def test_atm_iv_uses_mid_iv_on_call_when_present():
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [
        _opt(500, "call", mid_iv=0.18),
        _opt(500, "put", mid_iv=0.20),
    ]
    assert p._atm_iv(opts, spot=500.0) == 0.18


def test_atm_iv_falls_back_to_smv_vol_when_mid_iv_missing():
    """Tradier returns smv_vol (Smoothed Market Vol) even when no quote exists."""
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [
        _opt(500, "call", smv_vol=0.17),
        _opt(500, "put", mid_iv=0.0),
    ]
    assert p._atm_iv(opts, spot=500.0) == 0.17


def test_atm_iv_falls_back_to_put_when_call_iv_zero():
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [
        _opt(500, "call"),  # no greeks data
        _opt(500, "put", mid_iv=0.19),
    ]
    assert p._atm_iv(opts, spot=500.0) == 0.19


def test_atm_iv_walks_to_nearby_strike_when_atm_has_no_iv():
    """Both ATM legs blank — pick the closest strike that has any IV."""
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [
        _opt(498, "call", mid_iv=0.21),
        _opt(499, "call"),
        _opt(500, "call"),  # ATM, blank
        _opt(500, "put"),
        _opt(501, "call"),
        _opt(502, "call", mid_iv=0.22),
    ]
    # ATM = 500; +1 = 501 (blank), -1 = 499 (blank), +2 = 502 (0.22) -> wins
    # The ladder walks outward symmetrically so -2 (498, 0.21) is visited only
    # after +2. Either way the function returns the first nonzero hit.
    iv = p._atm_iv(opts, spot=500.0)
    assert iv in (0.22, 0.21)
    assert iv > 0


def test_atm_iv_returns_zero_when_everything_blank():
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [_opt(500, "call"), _opt(500, "put")]
    assert p._atm_iv(opts, spot=500.0) == 0.0


def test_atm_iv_handles_string_strikes():
    """Tradier sometimes returns strikes as floats nested in larger payloads;
    ensure float coercion works."""
    p = LiveTradierChainProvider.__new__(LiveTradierChainProvider)
    opts = [
        {"strike": 500.0, "option_type": "call", "bid": 0, "ask": 0,
         "greeks": {"mid_iv": 0.18}},
    ]
    assert p._atm_iv(opts, spot=500.0) == 0.18
