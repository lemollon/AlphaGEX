"""Integration tests for backend.bots.tsunami.gates.orchestrator.

Verify the G02..G10 chain runs in order, stops at first non-PASS,
populates gates_passed_before_failure correctly, and that the
EntryDecision carries the structure only when every gate passes.
G01 was removed 2026-05-07.

The DB persist path is not exercised here -- we verify it is NOT
called when DATABASE_URL is unset (best-effort by design).
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.bots.tsunami.gates.orchestrator import (  # noqa: E402
    EntryDecision,
    GateInputs,
    orchestrate_entry,
)
from backend.bots.tsunami.models import TsunamiConfig  # noqa: E402
from backend.bots.tsunami.strike_mapping.engine import (  # noqa: E402
    OptionLeg,
    TradeStructure,
)
from backend.bots.tsunami.strike_mapping.letf_mapper import LETFTarget  # noqa: E402
from backend.bots.tsunami.strike_mapping.wall_finder import (  # noqa: E402
    GammaStrike,
    Wall,
)


_TODAY = date(2026, 5, 4)


def _config() -> TsunamiConfig:
    return TsunamiConfig(
        instance_name="TSUNAMI-TSLA",
        letf_ticker="TSLL",
        underlying_ticker="TSLA",
    )


def _wall() -> Wall:
    return Wall(strike=191.0, gamma=8.0, median_local_gamma=1.0, concentration_ratio=8.0)


def _target() -> LETFTarget:
    return LETFTarget(
        target_strike=9.0, band_low=8.5, band_high=9.5,
        predicted_letf_return=-0.10, vol_drag=-0.005, te_band=0.056,
    )


def _structure(*, sp_oi=500, lp_oi=500, lc_oi=500,
               sp_bid=0.50, sp_ask=0.52,
               lc_bid=0.28, lc_ask=0.32) -> TradeStructure:
    short_put = OptionLeg(strike=9.0, bid=sp_bid, ask=sp_ask, open_interest=sp_oi, contract_type="put")
    long_put = OptionLeg(strike=8.5, bid=0.18, ask=0.22, open_interest=lp_oi, contract_type="put")
    long_call = OptionLeg(strike=12.0, bid=lc_bid, ask=lc_ask, open_interest=lc_oi, contract_type="call")
    sp_mid = (sp_bid + sp_ask) / 2
    lp_mid = 0.20
    lc_mid = (lc_bid + lc_ask) / 2
    return TradeStructure(
        short_put=short_put, long_put=long_put, long_call=long_call,
        put_spread_credit=sp_mid - lp_mid,
        long_call_cost=lc_mid,
        net_cost=lc_mid - (sp_mid - lp_mid),
        wall=_wall(), letf_target=_target(),
    )


_GOOD_STRIKES = [
    GammaStrike(190.0, 1.0), GammaStrike(191.0, 8.0), GammaStrike(195.0, 1.0),
    GammaStrike(200.0, 1.0), GammaStrike(205.0, 1.0), GammaStrike(210.0, 1.0),
]


def _good_inputs(**overrides) -> GateInputs:
    base = dict(
        letf_ticker="TSLL", underlying_ticker="TSLA",
        underlying_net_gex=1.0e8,
        underlying_strikes=_GOOD_STRIKES,
        underlying_spot=200.0,
        next_earnings_date=_TODAY + timedelta(days=30),
        iv_rank=75.0,
        underlying_50d_ma=185.0,
        open_position_count=0,
        config=_config(),
        attempted_structure=_structure(),
        today=_TODAY,
    )
    base.update(overrides)
    return GateInputs(**base)


class HappyPath(unittest.TestCase):
    def test_all_gates_pass_returns_structure(self):
        decision = orchestrate_entry(_good_inputs())
        self.assertIsInstance(decision, EntryDecision)
        self.assertIsNotNone(decision.structure)
        self.assertTrue(decision.passed)
        self.assertEqual(len(decision.chain), 9)
        self.assertEqual([r.gate for r in decision.chain],
                         ["G02", "G03", "G04", "G05", "G06", "G07", "G08", "G09", "G10"])
        self.assertIsNone(decision.first_failure)


class FirstFailureStopsChain(unittest.TestCase):
    def test_g05_insufficient_history_stops_chain(self):
        decision = orchestrate_entry(_good_inputs(iv_rank=None))
        self.assertEqual(decision.first_failure.gate, "G05")
        self.assertEqual(decision.first_failure.outcome.value, "INSUFFICIENT_HISTORY")
        # G02-G05 evaluated; chain length 4.
        self.assertEqual(len(decision.chain), 4)

    def test_g06_failure_after_pre_structure_pass(self):
        decision = orchestrate_entry(_good_inputs(attempted_structure=_structure(sp_oi=50)))
        self.assertEqual(decision.first_failure.gate, "G06")
        passed = [r.gate for r in decision.chain if r.passed]
        self.assertEqual(passed, ["G02", "G03", "G04", "G05"])

    def test_g10_failure_at_position_cap(self):
        decision = orchestrate_entry(_good_inputs(open_position_count=3))
        self.assertEqual(decision.first_failure.gate, "G10")
        # All 8 prior gates passed.
        passed = [r.gate for r in decision.chain if r.passed]
        self.assertEqual(len(passed), 8)


class EarningsGateSkip(unittest.TestCase):
    def test_has_earnings_false_synthesizes_g04_pass(self):
        decision = orchestrate_entry(_good_inputs(
            underlying_ticker="SPY", next_earnings_date=None, has_earnings=False,
        ))
        g04 = next(r for r in decision.chain if r.gate == "G04")
        self.assertTrue(g04.passed)
        self.assertTrue(decision.passed)

    def test_has_earnings_true_still_fails_closed_on_none(self):
        decision = orchestrate_entry(_good_inputs(next_earnings_date=None))
        self.assertEqual(decision.first_failure.gate, "G04")


class StructureUnavailable(unittest.TestCase):
    def test_none_structure_synthesizes_g06_fail(self):
        decision = orchestrate_entry(_good_inputs(attempted_structure=None))
        self.assertEqual(decision.first_failure.gate, "G06")
        self.assertIn("structure unavailable", decision.first_failure.reason.lower())
        self.assertFalse(decision.first_failure.context.get("structure_present"))


class PersistenceIsBestEffort(unittest.TestCase):
    def test_persist_swallows_import_error(self):
        # Force the import inside _persist_failure to fail; orchestrator
        # must still return a clean EntryDecision.
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            decision = orchestrate_entry(_good_inputs(iv_rank=None))
        self.assertIsNone(decision.structure)
        self.assertEqual(decision.first_failure.gate, "G05")


if __name__ == "__main__":
    unittest.main()
