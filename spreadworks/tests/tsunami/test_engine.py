"""Tests for backend.bots.tsunami.engine.TsunamiEngine."""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.bots.tsunami.configs import get  # noqa: E402
from backend.bots.tsunami.engine import (  # noqa: E402
    TsunamiEngine,
    MarketSnapshot,
    PlatformContext,
)
from backend.bots.tsunami.instance import TsunamiInstance  # noqa: E402
from backend.bots.tsunami.strike_mapping.engine import OptionLeg  # noqa: E402
from backend.bots.tsunami.strike_mapping.wall_finder import GammaStrike  # noqa: E402


_TODAY = datetime(2026, 5, 4, 14, 30, tzinfo=timezone.utc)
_FRIDAY = date(2026, 5, 8)


def _good_chain() -> dict:
    chain = {}
    for k in [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 11.5, 12.0, 12.5]:
        if k <= 10.0:
            # OTM put value must INCREASE with strike (see test_main.py note
            # on the inverted AlphaGEX-era fixture).
            mid = 0.20 + (k - 7.5) * 0.6
            chain[(k, "put")] = OptionLeg(k, mid - 0.02, mid + 0.02, 500, "put")
        else:
            chain[(k, "call")] = OptionLeg(k, 0.28, 0.32, 500, "call")
    chain[(12.0, "call")] = OptionLeg(12.0, 0.28, 0.32, 500, "call")
    return chain


def _good_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        underlying_net_gex=1.0e8,
        underlying_strikes=[
            GammaStrike(190.0, 1.0), GammaStrike(191.0, 8.0),
            GammaStrike(195.0, 1.0), GammaStrike(200.0, 1.0),
            GammaStrike(205.0, 1.0), GammaStrike(210.0, 1.0),
        ],
        underlying_spot=200.0,
        letf_spot=10.0,
        letf_chain=_good_chain(),
        sigma_annualized=0.5,
        next_earnings_date=date(2026, 6, 1),
        iv_rank=75.0,
        underlying_50d_ma=185.0,
    )


def _empty_platform() -> PlatformContext:
    return PlatformContext(open_position_count=0, open_dollars_at_risk=0.0)


class EvaluateEntryHappyPath(unittest.TestCase):
    def setUp(self):
        # is_killed reads from DB; force False so test doesn't depend on env.
        self._patch = patch("backend.bots.tsunami.instance.is_killed", return_value=False)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_returns_approved_structure_when_all_pass(self):
        engine = TsunamiEngine()
        inst = TsunamiInstance(config=get("TSUNAMI-TSLL"))
        decision = engine.evaluate_entry(
            inst, _good_snapshot(), _empty_platform(), now=_TODAY,
        )
        self.assertIsNotNone(decision.structure)
        self.assertGreater(decision.contracts_to_trade, 0)
        self.assertTrue(decision.approved)
        self.assertEqual(len(decision.gate_chain), 9)

    def test_sizing_picks_binding_constraint(self):
        engine = TsunamiEngine()
        inst = TsunamiInstance(config=get("TSUNAMI-TSLL"))
        decision = engine.evaluate_entry(
            inst, _good_snapshot(), _empty_platform(), now=_TODAY,
        )
        self.assertIsNotNone(decision.sizing)
        # spread width = $0.50, credit ~ $0.30 -> max_loss/contract = $20 dollars
        # per_trade $75 / $20 = 3 contracts; hard cap = 2; -> 2 contracts.
        self.assertIn(decision.sizing.binding_constraint,
                      ("hard_cap", "per_trade_risk"))


class EvaluateEntryGateFailures(unittest.TestCase):
    def setUp(self):
        self._patch = patch("backend.bots.tsunami.instance.is_killed", return_value=False)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_g05_cold_start_blocks_entry(self):
        engine = TsunamiEngine()
        inst = TsunamiInstance(config=get("TSUNAMI-TSLL"))
        snap = _good_snapshot()
        snap = MarketSnapshot(**{**snap.__dict__, "iv_rank": None})
        decision = engine.evaluate_entry(inst, snap, _empty_platform(), now=_TODAY)
        self.assertIsNone(decision.structure)
        self.assertEqual(decision.gate_chain[-1].gate, "G05")


class EvaluateEntryPlatformPressure(unittest.TestCase):
    def setUp(self):
        self._patch = patch("backend.bots.tsunami.instance.is_killed", return_value=False)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_g10_position_cap_blocks_entry(self):
        engine = TsunamiEngine()
        inst = TsunamiInstance(config=get("TSUNAMI-TSLL"))
        platform = PlatformContext(open_position_count=3, open_dollars_at_risk=0.0)
        decision = engine.evaluate_entry(inst, _good_snapshot(), platform, now=_TODAY)
        self.assertEqual(decision.gate_chain[-1].gate, "G10")
        self.assertIsNone(decision.structure)


class ManageOpenPositions(unittest.TestCase):
    def test_no_positions_returns_empty_list(self):
        engine = TsunamiEngine()
        inst = TsunamiInstance(config=get("TSUNAMI-TSLL"))
        actions = engine.manage_open_positions(inst, now=_TODAY)
        self.assertEqual(actions, [])


if __name__ == "__main__":
    unittest.main()
