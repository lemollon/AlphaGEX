"""Tests for trading.goliath.kill_switch.instance_triggers."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.kill_switch import KillScope  # noqa: E402
from trading.goliath.kill_switch.instance_triggers import (  # noqa: E402
    CONSECUTIVE_LOSS_THRESHOLD,
    DRAWDOWN_THRESHOLD,
    TRADES_WITHOUT_UPSIDE_THRESHOLD,
    evaluate_consecutive_losses,
    evaluate_drawdown,
    evaluate_trades_without_upside,
)


class IK1Drawdown(unittest.TestCase):
    def test_fires_above_30pct(self):
        evt = evaluate_drawdown("GOLIATH-MSTU", drawdown_pct=0.35)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "I-K1")
        self.assertEqual(evt.scope, KillScope.INSTANCE)
        self.assertEqual(evt.instance_name, "GOLIATH-MSTU")

    def test_does_not_fire_at_exactly_30pct(self):
        # Spec uses strict >, not >=.
        evt = evaluate_drawdown("GOLIATH-MSTU", drawdown_pct=DRAWDOWN_THRESHOLD)
        self.assertIsNone(evt)

    def test_does_not_fire_below_30pct(self):
        self.assertIsNone(evaluate_drawdown("GOLIATH-MSTU", drawdown_pct=0.20))

    def test_context_carries_pct(self):
        evt = evaluate_drawdown("GOLIATH-TSLL", drawdown_pct=0.40)
        self.assertEqual(evt.context["drawdown_pct"], 0.40)
        self.assertEqual(evt.context["threshold"], DRAWDOWN_THRESHOLD)


class IK2ConsecutiveLosses(unittest.TestCase):
    def test_fires_at_5(self):
        evt = evaluate_consecutive_losses("GOLIATH-NVDL", consecutive_losses=5)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "I-K2")

    def test_fires_above_5(self):
        evt = evaluate_consecutive_losses("GOLIATH-NVDL", consecutive_losses=10)
        self.assertIsNotNone(evt)

    def test_does_not_fire_at_4(self):
        self.assertIsNone(
            evaluate_consecutive_losses("GOLIATH-NVDL", consecutive_losses=4)
        )

    def test_does_not_fire_at_zero(self):
        self.assertIsNone(
            evaluate_consecutive_losses("GOLIATH-NVDL", consecutive_losses=0)
        )

    def test_threshold_constant_is_5(self):
        self.assertEqual(CONSECUTIVE_LOSS_THRESHOLD, 5)


class IK3TradesWithoutUpside(unittest.TestCase):
    def test_fires_at_20(self):
        evt = evaluate_trades_without_upside("GOLIATH-CONL", trades_without_upside=20)
        self.assertIsNotNone(evt)
        self.assertEqual(evt.trigger_id, "I-K3")

    def test_fires_above_20(self):
        evt = evaluate_trades_without_upside("GOLIATH-CONL", trades_without_upside=25)
        self.assertIsNotNone(evt)

    def test_does_not_fire_at_19(self):
        self.assertIsNone(
            evaluate_trades_without_upside("GOLIATH-CONL", trades_without_upside=19)
        )

    def test_threshold_constant_is_20(self):
        self.assertEqual(TRADES_WITHOUT_UPSIDE_THRESHOLD, 20)


if __name__ == "__main__":
    unittest.main()
