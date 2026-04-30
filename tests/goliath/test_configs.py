"""Tests for trading.goliath.configs."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from trading.goliath.configs import (  # noqa: E402
    GLOBAL,
    GOLIATH_INSTANCES,
    InstanceConfig,
    all_instances,
    get,
)


class GlobalConfig(unittest.TestCase):
    def test_account_capital_5k(self):
        self.assertEqual(GLOBAL.account_capital, 5000.0)

    def test_platform_cap_750(self):
        self.assertEqual(GLOBAL.platform_cap, 750.0)

    def test_max_concurrent_3(self):
        self.assertEqual(GLOBAL.max_concurrent_positions, 3)

    def test_paper_only_default(self):
        self.assertTrue(GLOBAL.paper_only)


class InstanceRegistry(unittest.TestCase):
    def test_five_instances(self):
        self.assertEqual(len(GOLIATH_INSTANCES), 5)

    def test_universe_coverage(self):
        names = {cfg.letf_ticker for cfg in all_instances()}
        self.assertEqual(names, {"MSTU", "TSLL", "NVDL", "CONL", "AMDL"})

    def test_underlying_pairs(self):
        pairs = {cfg.letf_ticker: cfg.underlying_ticker for cfg in all_instances()}
        self.assertEqual(pairs, {
            "MSTU": "MSTR", "TSLL": "TSLA", "NVDL": "NVDA",
            "CONL": "COIN", "AMDL": "AMD",
        })

    def test_allocation_caps_per_spec(self):
        caps = {cfg.letf_ticker: cfg.allocation_cap for cfg in all_instances()}
        self.assertEqual(caps["MSTU"], 200.0)
        self.assertEqual(caps["TSLL"], 200.0)
        self.assertEqual(caps["NVDL"], 200.0)
        self.assertEqual(caps["CONL"], 150.0)
        self.assertEqual(caps["AMDL"], 150.0)

    def test_all_paper_only(self):
        for cfg in all_instances():
            self.assertTrue(cfg.paper_only, f"{cfg.bot_guard_tag} must be paper_only")

    def test_bot_guard_tags_namespaced(self):
        for cfg in all_instances():
            self.assertTrue(cfg.bot_guard_tag.startswith("GOLIATH-"))


class GetLookup(unittest.TestCase):
    def test_get_returns_config(self):
        cfg = get("GOLIATH-MSTU")
        self.assertIsInstance(cfg, InstanceConfig)
        self.assertEqual(cfg.letf_ticker, "MSTU")

    def test_get_uppercases(self):
        cfg = get("goliath-tsll")
        self.assertEqual(cfg.letf_ticker, "TSLL")

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError):
            get("GOLIATH-UNKNOWN")


if __name__ == "__main__":
    unittest.main()
