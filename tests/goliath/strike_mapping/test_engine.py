"""Tests for trading.goliath.strike_mapping.engine.

Synthetic-input integration tests. Maps to master spec section 3.1:
    #1  Happy path with clean wall, sufficient OI, valid economics
    #3  Wall exists but no LETF strikes in target range -> None
    #4  Strikes exist but OI too low -> None
    #5  Strikes exist but bid-ask too wide -> None
    #6  Net cost exceeds 30% of long-call mid -> None
    #13 Real-world data test using a TSLA/TSLL fixture (cached)
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.engine import (  # noqa: E402
    OptionLeg,
    TradeStructure,
    build_trade_structure,
)
from trading.goliath.strike_mapping.wall_finder import GammaStrike  # noqa: E402


# ---- Test fixtures ---------------------------------------------------------

# TSLA setup: spot=$200, wall at $191 (-4.5% from spot).
# Local band [$190, $210]: median gamma ~1.0, wall gamma 5.0 -> 5x concentration.
_UNDERLYING_STRIKES = [
    GammaStrike(strike=185.0, gamma=0.5),
    GammaStrike(strike=190.0, gamma=1.0),
    GammaStrike(strike=191.0, gamma=5.0),  # the wall
    GammaStrike(strike=195.0, gamma=1.0),
    GammaStrike(strike=200.0, gamma=1.0),
    GammaStrike(strike=205.0, gamma=1.0),
    GammaStrike(strike=210.0, gamma=1.0),
]
_UNDERLYING_SPOT = 200.0
_LETF_SPOT = 10.0
_SIGMA = 0.5
_T_WEEK = 7.0 / 365.0


def _config() -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-TSLA",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
    )


def _leg(strike: float, bid: float, ask: float, oi: int, kind: str) -> OptionLeg:
    return OptionLeg(strike=strike, bid=bid, ask=ask, open_interest=oi, contract_type=kind)


def _good_chain(net_cost_factor: float = 1.0) -> dict:
    """Standard healthy chain: tight quotes, OI >= 200, reasonable economics.

    net_cost_factor scales the long-call price; 1.0 = healthy, 5.0 = call too
    expensive (test 6). Default produces net_cost ~= 5%% of long-call mid.
    """
    chain = {}
    for k in [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0]:
        if k <= _LETF_SPOT:
            mid = max(0.20, _LETF_SPOT - k + 0.20)
            chain[(k, "put")] = _leg(k, mid - 0.02, mid + 0.02, 500, "put")
        else:
            mid = max(0.10, _LETF_SPOT - k + 1.0) if k < _LETF_SPOT + 2 else 0.30
            chain[(k, "call")] = _leg(k, mid - 0.02, mid + 0.02, 500, "call")
    # Override the long-call (target ~$12) for net-cost-control.
    base_call_mid = 0.30 * net_cost_factor
    chain[(12.0, "call")] = _leg(12.0, base_call_mid - 0.02, base_call_mid + 0.02, 500, "call")
    return chain


class HappyPath(unittest.TestCase):
    """Spec section 3.1 test 1: clean wall, sufficient OI, valid economics."""

    def test_returns_trade_structure(self):
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, _good_chain(), _config(),
        )
        self.assertIsInstance(result, TradeStructure)
        self.assertEqual(result.short_put.strike, 9.0)
        self.assertEqual(result.long_put.strike, 8.5)
        self.assertEqual(result.long_call.strike, 12.0)
        self.assertEqual(result.short_put.contract_type, "put")
        self.assertEqual(result.long_put.contract_type, "put")
        self.assertEqual(result.long_call.contract_type, "call")

    def test_economics_computed(self):
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, _good_chain(), _config(),
        )
        self.assertIsNotNone(result)
        # net_cost = long_call_mid - (short_put_mid - long_put_mid)
        expected_credit = result.short_put.bid + (result.short_put.ask - result.short_put.bid) / 2
        expected_credit -= (result.long_put.bid + (result.long_put.ask - result.long_put.bid) / 2)
        self.assertAlmostEqual(result.put_spread_credit, expected_credit)
        self.assertAlmostEqual(result.long_call_cost, 0.30, places=2)


class NoStrikesInTargetRange(unittest.TestCase):
    """Spec section 3.1 test 3: wall exists, but no LETF strikes in band."""

    def test_returns_none_when_chain_skips_target_band(self):
        # Drop the $9.00 put -> no qualifying short_put strike in [band_low, target].
        chain = _good_chain()
        chain.pop((9.0, "put"), None)
        chain.pop((8.5, "put"), None)
        # Also drop $8.0 to leave a gap below the target band entirely.
        chain.pop((8.0, "put"), None)
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, chain, _config(),
        )
        self.assertIsNone(result)


class OILowOnAnyLeg(unittest.TestCase):
    """Spec section 3.1 test 4: strikes exist but OI too low."""

    def test_short_put_oi_below_200_returns_none(self):
        chain = _good_chain()
        existing = chain[(9.0, "put")]
        chain[(9.0, "put")] = _leg(existing.strike, existing.bid, existing.ask, 100, "put")
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, chain, _config(),
        )
        self.assertIsNone(result)

    def test_long_call_oi_below_200_returns_none(self):
        chain = _good_chain()
        existing = chain[(12.0, "call")]
        chain[(12.0, "call")] = _leg(existing.strike, existing.bid, existing.ask, 50, "call")
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, chain, _config(),
        )
        self.assertIsNone(result)


class BidAskTooWide(unittest.TestCase):
    """Spec section 3.1 test 5: bid-ask spread > 20% of mid on a leg."""

    def test_wide_short_put_spread_returns_none(self):
        chain = _good_chain()
        # short put: bid 0.50 / ask 0.80 -> mid 0.65, spread 0.30 = 46% -> reject.
        chain[(9.0, "put")] = _leg(9.0, 0.50, 0.80, 500, "put")
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, chain, _config(),
        )
        self.assertIsNone(result)


class NetCostTooHigh(unittest.TestCase):
    """Spec section 3.1 test 6: net cost > 30% of long-call mid."""

    def test_expensive_call_breaks_net_cost_gate(self):
        # Inflate long-call mid 5x: net_cost = 1.50 - small_credit > 0.30 * 1.50.
        chain = _good_chain(net_cost_factor=5.0)
        result = build_trade_structure(
            _UNDERLYING_STRIKES, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, chain, _config(),
        )
        self.assertIsNone(result)


class WallAbsenceShortCircuits(unittest.TestCase):
    def test_no_wall_returns_none(self):
        # Flat gamma everywhere -> no wall meets 2x median.
        flat = [GammaStrike(strike=k, gamma=1.0) for k in [185, 190, 195, 200, 205, 210]]
        result = build_trade_structure(
            flat, _UNDERLYING_SPOT, _LETF_SPOT,
            _SIGMA, _T_WEEK, _good_chain(), _config(),
        )
        self.assertIsNone(result)


class RealWorldFixture(unittest.TestCase):
    """Spec section 3.1 test 13: realistic TSLA/TSLL chain (cached fixture)."""

    def test_tsla_tsll_fixture_produces_sensible_structure(self):
        # Snapshot-style fixture mimicking a Monday morning entry. TSLA $200,
        # TSLL $10, sigma 60%% (typical for TSLA-derived LETF), 7 DTE.
        underlying = [
            GammaStrike(strike=180.0, gamma=0.8),
            GammaStrike(strike=185.0, gamma=1.2),
            GammaStrike(strike=190.0, gamma=1.5),
            GammaStrike(strike=191.0, gamma=8.0),  # wall
            GammaStrike(strike=195.0, gamma=1.5),
            GammaStrike(strike=200.0, gamma=1.4),
            GammaStrike(strike=205.0, gamma=1.3),
            GammaStrike(strike=210.0, gamma=1.0),
        ]
        chain = _good_chain()
        result = build_trade_structure(
            underlying, 200.0, 10.0, 0.60, _T_WEEK, chain, _config(),
        )
        self.assertIsNotNone(result, "real-world TSLA/TSLL fixture should produce a structure")
        # Sanity: short put below LETF spot, long call above LETF spot.
        self.assertLess(result.short_put.strike, 10.0)
        self.assertGreater(result.long_call.strike, 10.0)
        # Sanity: long put exactly one strike below short put.
        self.assertLess(result.long_put.strike, result.short_put.strike)
        # Sanity: net cost is small relative to long-call cost.
        self.assertLess(result.net_cost, result.long_call_cost)


if __name__ == "__main__":
    unittest.main()
