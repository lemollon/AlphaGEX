"""Tests for trading.goliath.gates.g03_wall_present."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from trading.goliath.gates import GateOutcome  # noqa: E402
from trading.goliath.gates.g03_wall_present import evaluate  # noqa: E402
from trading.goliath.models import GoliathConfig  # noqa: E402
from trading.goliath.strike_mapping.wall_finder import GammaStrike  # noqa: E402


def _config() -> GoliathConfig:
    return GoliathConfig(
        instance_name="GOLIATH-T",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
    )


class G03WallPresent(unittest.TestCase):
    def test_passes_when_wall_present(self):
        strikes = [
            GammaStrike(190.0, 1.0),
            GammaStrike(192.0, 5.0),  # wall
            GammaStrike(195.0, 1.0),
            GammaStrike(200.0, 1.0),
            GammaStrike(205.0, 1.0),
            GammaStrike(210.0, 1.0),
        ]
        result = evaluate(strikes, 200.0, _config())
        self.assertEqual(result.gate, "G03")
        self.assertEqual(result.outcome, GateOutcome.PASS)
        self.assertEqual(result.context["wall_strike"], 192.0)
        self.assertAlmostEqual(result.context["wall_concentration_ratio"], 5.0)

    def test_fails_when_no_wall(self):
        strikes = [GammaStrike(s, 1.0) for s in [190, 195, 200, 205, 210]]
        result = evaluate(strikes, 200.0, _config())
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertIn("No wall", result.reason)

    def test_fails_when_only_above_spot_walls(self):
        strikes = [
            GammaStrike(195.0, 1.0),
            GammaStrike(200.0, 1.0),
            GammaStrike(205.0, 1.0),
            GammaStrike(208.0, 10.0),  # wall above spot -- ignored
        ]
        result = evaluate(strikes, 200.0, _config())
        self.assertEqual(result.outcome, GateOutcome.FAIL)

    def test_fails_with_empty_strikes(self):
        result = evaluate([], 200.0, _config())
        self.assertEqual(result.outcome, GateOutcome.FAIL)
        self.assertEqual(result.context["n_strikes"], 0)


if __name__ == "__main__":
    unittest.main()
