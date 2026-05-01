"""Tests for trading.goliath.kill_switch.platform_triggers."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.kill_switch import KillScope  # noqa: E402
from trading.goliath.kill_switch.platform_triggers import (  # noqa: E402
    PLATFORM_DRAWDOWN_THRESHOLD,
    SINGLE_TRADE_LOSS_MULTIPLIER,
    TV_API_DOWN_HOURS_THRESHOLD,
    VIX_LEVEL_THRESHOLD,
    VIX_SUSTAINED_DAYS_THRESHOLD,
    evaluate_platform_drawdown,
    evaluate_single_trade_loss,
    evaluate_tv_api_down,
    evaluate_vix_sustained,
)


class PK1PlatformDrawdown(unittest.TestCase):
    def test_fires_above_15pct(self):
        evt = evaluate_platform_drawdown(platform_drawdown_pct=0.20)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "P-K1")
        self.assertEqual(evt.scope, KillScope.PLATFORM)
        self.assertIsNone(evt.instance_name)

    def test_does_not_fire_at_exactly_15pct(self):
        self.assertIsNone(evaluate_platform_drawdown(PLATFORM_DRAWDOWN_THRESHOLD))

    def test_does_not_fire_below_15pct(self):
        self.assertIsNone(evaluate_platform_drawdown(0.05))


class PK2SingleTradeLoss(unittest.TestCase):
    def test_fires_above_1_5x_defined_max(self):
        evt = evaluate_single_trade_loss(
            last_trade_loss_dollars=40.0,
            last_trade_defined_max=20.0,
        )
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "P-K2")
        self.assertEqual(evt.context["threshold_multiplier"], 1.5)

    def test_does_not_fire_at_exact_threshold(self):
        # Loss exactly 1.5x -> spec says strictly greater -> no fire.
        evt = evaluate_single_trade_loss(
            last_trade_loss_dollars=30.0,
            last_trade_defined_max=20.0,
        )
        self.assertIsNone(evt)

    def test_does_not_fire_below_threshold(self):
        evt = evaluate_single_trade_loss(
            last_trade_loss_dollars=15.0,
            last_trade_defined_max=20.0,
        )
        self.assertIsNone(evt)

    def test_does_not_fire_when_winner(self):
        evt = evaluate_single_trade_loss(
            last_trade_loss_dollars=0.0,
            last_trade_defined_max=20.0,
        )
        self.assertIsNone(evt)

    def test_does_not_fire_with_invalid_defined_max(self):
        self.assertIsNone(evaluate_single_trade_loss(40.0, 0.0))
        self.assertIsNone(evaluate_single_trade_loss(40.0, -5.0))


class PK3VIXSustained(unittest.TestCase):
    def test_fires_when_vix_high_and_3_days_sustained(self):
        evt = evaluate_vix_sustained(current_vix=40.0, days_above_threshold=3)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "P-K3")

    def test_does_not_fire_with_only_2_days(self):
        evt = evaluate_vix_sustained(current_vix=40.0, days_above_threshold=2)
        self.assertIsNone(evt)

    def test_does_not_fire_with_low_vix(self):
        # Even at 5 days, VIX 30 is below the level threshold.
        evt = evaluate_vix_sustained(current_vix=30.0, days_above_threshold=5)
        self.assertIsNone(evt)

    def test_thresholds_match_spec(self):
        self.assertEqual(VIX_LEVEL_THRESHOLD, 35.0)
        self.assertEqual(VIX_SUSTAINED_DAYS_THRESHOLD, 3)


class PK4TVAPIDown(unittest.TestCase):
    def test_fires_above_24_hours(self):
        evt = evaluate_tv_api_down(tv_api_down_hours=25.0)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "P-K4")

    def test_does_not_fire_at_exactly_24h(self):
        self.assertIsNone(
            evaluate_tv_api_down(TV_API_DOWN_HOURS_THRESHOLD * 1.0)
        )

    def test_does_not_fire_below_24h(self):
        self.assertIsNone(evaluate_tv_api_down(12.0))


class ConstantsAndThresholds(unittest.TestCase):
    def test_single_trade_loss_multiplier_is_1_5(self):
        self.assertEqual(SINGLE_TRADE_LOSS_MULTIPLIER, 1.5)


if __name__ == "__main__":
    unittest.main()
