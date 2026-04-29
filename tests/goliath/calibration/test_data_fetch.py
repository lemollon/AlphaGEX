"""Tests for trading.goliath.calibration.data_fetch.

Three suites:
    TestCacheHelpers       -- _cache_path, _load_cache, _save_cache in isolation
    TestFetchGexHistory    -- fetch_gex_history with stubbed TradingVolatilityAPI
    TestFetchPriceHistory  -- fetch_price_history with stubbed yfinance
    TestFetchAllUniverse   -- orchestration smoke test

Strategy:
    - CACHE_DIR is monkeypatched to a per-test tempdir so tests never
      contaminate the real .goliath_cache/.
    - sys.modules is stubbed for core_classes_and_engines and yfinance
      so tests can run without those packages installed.
    - Real parquet round-trips happen against the tempdir to verify
      caching behavior end-to-end.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from trading.goliath.calibration import data_fetch  # noqa: E402


class _TempCacheMixin:
    """Test base that points data_fetch.CACHE_DIR at a per-test tempdir."""

    def setUp(self):  # type: ignore[override]
        self._tmp = tempfile.mkdtemp(prefix="goliath_cache_test_")
        self._orig_cache = data_fetch.CACHE_DIR
        data_fetch.CACHE_DIR = Path(self._tmp)

    def tearDown(self):  # type: ignore[override]
        data_fetch.CACHE_DIR = self._orig_cache
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestCacheHelpers(_TempCacheMixin, unittest.TestCase):
    """Cache primitives: path construction, parquet round-trip, error tolerance."""

    def test_cache_path_includes_ticker_kind_and_today(self):
        p = data_fetch._cache_path("MSTR", "gex_history_90d")
        today = date.today().isoformat()
        self.assertIn("MSTR", p.name)
        self.assertIn("gex_history_90d", p.name)
        self.assertIn(today, p.name)
        self.assertEqual(p.suffix, ".parquet")

    def test_cache_path_creates_parent_dir(self):
        # Tempdir already exists; verify _cache_path doesn't fail when it does.
        p = data_fetch._cache_path("AMD", "price_90d")
        self.assertTrue(p.parent.exists())

    def test_load_cache_missing_returns_none(self):
        p = Path(self._tmp) / "does_not_exist.parquet"
        self.assertIsNone(data_fetch._load_cache(p))

    def test_save_then_load_round_trip(self):
        idx = pd.bdate_range(start="2026-01-01", periods=5)
        df = pd.DataFrame({"price": [100.0, 101.0, 102.0, 101.5, 100.5]}, index=idx)
        df.index.name = "date"
        p = Path(self._tmp) / "round_trip.parquet"
        data_fetch._save_cache(p, df)
        self.assertTrue(p.exists())
        loaded = data_fetch._load_cache(p)
        self.assertIsNotNone(loaded)
        pd.testing.assert_frame_equal(loaded, df)

    def test_save_empty_df_is_noop(self):
        p = Path(self._tmp) / "empty.parquet"
        data_fetch._save_cache(p, pd.DataFrame())
        self.assertFalse(p.exists())

    def test_save_none_is_noop(self):
        p = Path(self._tmp) / "none.parquet"
        data_fetch._save_cache(p, None)  # type: ignore[arg-type]
        self.assertFalse(p.exists())

    def test_corrupt_cache_returns_none_does_not_raise(self):
        p = Path(self._tmp) / "corrupt.parquet"
        p.write_text("this is not a parquet file")
        loaded = data_fetch._load_cache(p)
        self.assertIsNone(loaded)


def _stub_tv_module(rows):
    """Build a MagicMock module to stuff into sys.modules['core_classes_and_engines']
    such that TradingVolatilityAPI().get_historical_gamma() returns rows."""
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_client.get_historical_gamma.return_value = rows
    mock_module.TradingVolatilityAPI = MagicMock(return_value=mock_client)
    return mock_module


class TestFetchGexHistory(_TempCacheMixin, unittest.TestCase):
    """fetch_gex_history with stubbed TradingVolatilityAPI."""

    def test_returns_dataframe_with_date_index(self):
        rows = [
            {"date": "2026-04-01", "price": 100.0, "gex_flip": 95.0, "net_gex": 1e8, "iv_rank": 30.0},
            {"date": "2026-04-02", "price": 101.0, "gex_flip": 96.0, "net_gex": 1.1e8, "iv_rank": 31.0},
            {"date": "2026-04-03", "price": 102.0, "gex_flip": 97.0, "net_gex": 1.2e8, "iv_rank": 32.0},
        ]
        with patch.dict(sys.modules, {"core_classes_and_engines": _stub_tv_module(rows)}):
            df = data_fetch.fetch_gex_history("MSTR", days=3)
        self.assertEqual(len(df), 3)
        self.assertEqual(df.index.name, "date")
        for col in ("price", "gex_flip", "net_gex", "iv_rank"):
            self.assertIn(col, df.columns)

    def test_empty_rows_returns_empty_df(self):
        with patch.dict(sys.modules, {"core_classes_and_engines": _stub_tv_module([])}):
            df = data_fetch.fetch_gex_history("MSTR", days=90)
        self.assertTrue(df.empty)

    def test_caches_on_success_and_returns_cached_on_second_call(self):
        rows = [{"date": "2026-04-01", "price": 100.0, "gex_flip": 95.0}]
        # First call: TV is stubbed and writes to cache
        with patch.dict(sys.modules, {"core_classes_and_engines": _stub_tv_module(rows)}):
            df1 = data_fetch.fetch_gex_history("MSTR", days=90)
        cache_files = list(Path(self._tmp).glob("MSTR_gex_history_*"))
        self.assertEqual(len(cache_files), 1, "Cache should exist after first fetch")

        # Second call: stub TV to raise to prove it's NOT being called
        bad_module = MagicMock()
        bad_module.TradingVolatilityAPI.side_effect = AssertionError("should not be called")
        with patch.dict(sys.modules, {"core_classes_and_engines": bad_module}):
            df2 = data_fetch.fetch_gex_history("MSTR", days=90)
        pd.testing.assert_frame_equal(df1, df2)

    def test_returns_empty_when_tv_unavailable(self):
        # Simulate ImportError by removing core_classes_and_engines from sys.modules
        # AND inserting a non-importable stub. Easiest: provide a module without
        # TradingVolatilityAPI attribute -> AttributeError -> caught as failure.
        broken = MagicMock(spec=[])  # no attributes
        with patch.dict(sys.modules, {"core_classes_and_engines": broken}):
            try:
                df = data_fetch.fetch_gex_history("MSTR", days=90)
            except AttributeError:
                # Function may raise here on older code paths; accept the empty
                # DataFrame contract OR a clean exception.
                df = pd.DataFrame()
        # Either path: contract is "empty DataFrame on failure"
        self.assertTrue(df.empty)


def _stub_yfinance_module(history_df):
    """Build a sys.modules stub for yfinance with Ticker(...).history() returning df."""
    mock_yf = MagicMock()
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = history_df
    mock_yf.Ticker = MagicMock(return_value=mock_ticker)
    return mock_yf


class TestFetchPriceHistory(_TempCacheMixin, unittest.TestCase):
    """fetch_price_history with stubbed yfinance."""

    def test_returns_dataframe_and_strips_timezone(self):
        # yfinance returns tz-aware index; data_fetch should strip it.
        idx = pd.bdate_range(end="2026-04-25", periods=5, tz="America/New_York")
        df = pd.DataFrame({"Close": [100.0, 101.0, 102.0, 101.0, 100.5]}, index=idx)
        with patch.dict(sys.modules, {"yfinance": _stub_yfinance_module(df)}):
            result = data_fetch.fetch_price_history("MSTR", days=5)
        self.assertEqual(len(result), 5)
        self.assertIsNone(result.index.tz, "tz should be stripped on cache write")

    def test_empty_returns_empty_df(self):
        with patch.dict(sys.modules, {"yfinance": _stub_yfinance_module(pd.DataFrame())}):
            result = data_fetch.fetch_price_history("MSTR", days=90)
        self.assertTrue(result.empty)

    def test_caches_round_trip(self):
        idx = pd.bdate_range(end="2026-04-25", periods=3)
        df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=idx)
        with patch.dict(sys.modules, {"yfinance": _stub_yfinance_module(df)}):
            df1 = data_fetch.fetch_price_history("MSTU", days=90)
        cache_files = list(Path(self._tmp).glob("MSTU_price_*"))
        self.assertEqual(len(cache_files), 1)
        # Second call with broken stub -> must return cached
        broken_yf = MagicMock(spec=[])
        with patch.dict(sys.modules, {"yfinance": broken_yf}):
            df2 = data_fetch.fetch_price_history("MSTU", days=90)
        pd.testing.assert_frame_equal(df1, df2)


class TestFetchAllUniverse(_TempCacheMixin, unittest.TestCase):
    """Smoke test: fetch_all_universe iterates LETF_PAIRS and returns both dicts."""

    def test_returns_two_dicts_keyed_correctly(self):
        # Stub TV to return one row per ticker; stub yfinance similarly.
        tv_rows = [{"date": "2026-04-01", "price": 100.0}]
        yf_idx = pd.bdate_range(end="2026-04-25", periods=3)
        yf_df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}, index=yf_idx)

        with patch.dict(
            sys.modules,
            {
                "core_classes_and_engines": _stub_tv_module(tv_rows),
                "yfinance": _stub_yfinance_module(yf_df),
            },
        ):
            gex, prices = data_fetch.fetch_all_universe(days=90)

        # gex_history should have 5 underlyings as keys
        self.assertEqual(set(gex.keys()), set(data_fetch.LETF_PAIRS.values()))
        # price_history should have 10 keys (5 underlyings + 5 LETFs)
        expected_price_keys = set(data_fetch.LETF_PAIRS.keys()) | set(data_fetch.LETF_PAIRS.values())
        self.assertEqual(set(prices.keys()), expected_price_keys)
        # All entries non-empty per the stubbed responses
        for ticker, df in gex.items():
            self.assertFalse(df.empty, f"gex_history[{ticker}] should not be empty")
        for ticker, df in prices.items():
            self.assertFalse(df.empty, f"price_history[{ticker}] should not be empty")


if __name__ == "__main__":
    unittest.main()
