"""Tests for trading.goliath.sizing.calculator.

Per kickoff prompt: 4 sizing scenarios required, one per binding constraint.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.sizing import (  # noqa: E402
    HARD_CAP_PER_TRADE,
    PLATFORM_TOTAL_CAP,
    calculate_contracts,
    instance_cap,
    per_trade_risk_dollars,
)


class HardCapBinds(unittest.TestCase):
    """Scenario 1: hard cap (2 contracts) is the smallest constraint."""

    def test_hard_cap_binds_when_other_limits_are_high(self):
        # max_loss $5 -> per_trade allows $75/$5 = 15 contracts
        # instance $200/$5 = 40 contracts; platform $750/$5 = 150 contracts
        # all >> 2 -> hard cap binds
        result = calculate_contracts(
            letf_ticker="MSTU",
            defined_max_loss_per_contract=5.0,
            instance_open_dollars=0.0,
            platform_open_dollars=0.0,
        )
        self.assertEqual(result.contracts, HARD_CAP_PER_TRADE)
        self.assertEqual(result.binding_constraint, "hard_cap")


class PerTradeRiskBinds(unittest.TestCase):
    """Scenario 2: per-trade $75 limit is the smallest constraint."""

    def test_per_trade_risk_binds_at_high_max_loss(self):
        # max_loss $50 -> per_trade $75/$50 = 1 contract
        # instance $200/$50 = 4; platform $750/$50 = 15; hard = 2
        # 1 < 2 < 4 < 15 -> per_trade binds
        result = calculate_contracts(
            letf_ticker="MSTU",
            defined_max_loss_per_contract=50.0,
        )
        self.assertEqual(result.contracts, 1)
        self.assertEqual(result.binding_constraint, "per_trade_risk")
        self.assertEqual(result.by_per_trade_risk, 1)


class InstanceCapBinds(unittest.TestCase):
    """Scenario 3: instance allocation remaining is the smallest constraint."""

    def test_instance_cap_binds_when_partially_filled(self):
        # MSTU cap $200; already $190 open -> remaining $10
        # max_loss $10 -> by_instance = 1
        # by_per_trade = 75/10 = 7; platform 750/10 = 75; hard = 2
        # 1 < 2 < 7 < 75 -> instance binds
        result = calculate_contracts(
            letf_ticker="MSTU",
            defined_max_loss_per_contract=10.0,
            instance_open_dollars=190.0,
        )
        self.assertEqual(result.contracts, 1)
        self.assertEqual(result.binding_constraint, "instance_cap")
        self.assertEqual(result.by_instance_remaining, 1)


class PlatformCapBinds(unittest.TestCase):
    """Scenario 4: platform $750 cap remaining is the smallest constraint."""

    def test_platform_cap_binds_when_near_total(self):
        # Platform cap $750, already $740 open -> remaining $10
        # max_loss $10 -> by_platform = 1
        # CONL cap $150, $0 open -> by_instance = 15
        # by_per_trade = 7, hard = 2
        # 1 < 2 < 7 < 15 -> platform binds
        result = calculate_contracts(
            letf_ticker="CONL",
            defined_max_loss_per_contract=10.0,
            instance_open_dollars=0.0,
            platform_open_dollars=740.0,
        )
        self.assertEqual(result.contracts, 1)
        self.assertEqual(result.binding_constraint, "platform_cap")
        self.assertEqual(result.by_platform_remaining, 1)


class ZeroAllocation(unittest.TestCase):
    def test_returns_zero_when_instance_cap_exhausted(self):
        # Instance fully utilized; calculator must return 0 contracts.
        result = calculate_contracts(
            letf_ticker="MSTU",
            defined_max_loss_per_contract=10.0,
            instance_open_dollars=200.0,  # full
        )
        self.assertEqual(result.contracts, 0)

    def test_returns_zero_when_platform_full(self):
        result = calculate_contracts(
            letf_ticker="CONL",
            defined_max_loss_per_contract=10.0,
            platform_open_dollars=PLATFORM_TOTAL_CAP,
        )
        self.assertEqual(result.contracts, 0)

    def test_returns_zero_for_unknown_letf(self):
        # Unknown LETF -> instance_cap = 0 -> by_instance = 0
        result = calculate_contracts(
            letf_ticker="UNKNOWN",
            defined_max_loss_per_contract=10.0,
        )
        self.assertEqual(result.contracts, 0)

    def test_returns_zero_for_invalid_max_loss(self):
        result = calculate_contracts(
            letf_ticker="MSTU",
            defined_max_loss_per_contract=0.0,
        )
        self.assertEqual(result.contracts, 0)
        self.assertEqual(result.binding_constraint, "invalid_max_loss")


class LimitsConstants(unittest.TestCase):
    def test_per_trade_risk_is_75(self):
        self.assertAlmostEqual(per_trade_risk_dollars(), 75.0)

    def test_instance_caps_match_spec(self):
        self.assertEqual(instance_cap("MSTU"), 200.0)
        self.assertEqual(instance_cap("TSLL"), 200.0)
        self.assertEqual(instance_cap("NVDL"), 200.0)
        self.assertEqual(instance_cap("CONL"), 150.0)
        self.assertEqual(instance_cap("AMDL"), 150.0)

    def test_platform_cap_is_750(self):
        self.assertEqual(PLATFORM_TOTAL_CAP, 750.0)

    def test_hard_cap_is_2(self):
        self.assertEqual(HARD_CAP_PER_TRADE, 2)


if __name__ == "__main__":
    unittest.main()
