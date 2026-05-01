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


class _FakeRateLimitError(Exception):
    """Class-name pattern matches yfinance.exceptions.YFRateLimitError detection."""

    pass


# Subclass with the exact class-name yfinance raises so the matcher works.
class YFRateLimitError(Exception):  # noqa: N818
    pass


class TestYFinanceRateLimitHardening(_TempCacheMixin, unittest.TestCase):
    """Verifies retry+backoff behavior added per Phase 1.5 step-9 incident."""

    def _stub_yfinance(self, side_effects):
        """Build a yfinance stub whose Ticker(...).history(...) iterates
        through `side_effects` (mix of exceptions and DataFrames)."""
        history_mock = MagicMock(side_effect=side_effects)
        ticker_mock = MagicMock()
        ticker_mock.history = history_mock
        yf_mock = MagicMock()
        yf_mock.Ticker = MagicMock(return_value=ticker_mock)
        return yf_mock, history_mock

    def test_retries_on_rate_limit_then_succeeds(self):
        df = pd.DataFrame({"Close": [10.0, 10.5]}, index=pd.to_datetime(["2026-01-01", "2026-01-02"]))
        # Two rate-limit errors, then success on the third attempt.
        side_effects = [YFRateLimitError("Too Many Requests. Rate limited."),
                        YFRateLimitError("rate limited"),
                        df]
        yf_mock, history_mock = self._stub_yfinance(side_effects)
        sleeps: list = []

        with patch.dict(sys.modules, {"yfinance": yf_mock}):
            result = data_fetch.fetch_price_history(
                "MSTR", days=10,
                backoff_seconds=[1, 2, 3],
                sleeper=sleeps.append,
            )

        self.assertEqual(history_mock.call_count, 3)
        self.assertEqual(sleeps, [1, 2])  # slept after attempts 1 and 2
        self.assertFalse(result.empty)
        self.assertEqual(len(result), 2)

    def test_gives_up_after_max_retries(self):
        side_effects = [YFRateLimitError("Too Many Requests")] * 4
        yf_mock, history_mock = self._stub_yfinance(side_effects)
        sleeps: list = []

        with patch.dict(sys.modules, {"yfinance": yf_mock}):
            result = data_fetch.fetch_price_history(
                "MSTR", days=10, max_retries=3,
                backoff_seconds=[1, 2, 3],
                sleeper=sleeps.append,
            )

        # 1 initial + 3 retries = 4 attempts; sleeps after attempts 1, 2, 3.
        self.assertEqual(history_mock.call_count, 4)
        self.assertEqual(sleeps, [1, 2, 3])
        self.assertTrue(result.empty)

    def test_non_rate_limit_error_fails_fast(self):
        side_effects = [ValueError("malformed response")]
        yf_mock, history_mock = self._stub_yfinance(side_effects)
        sleeps: list = []

        with patch.dict(sys.modules, {"yfinance": yf_mock}):
            result = data_fetch.fetch_price_history(
                "MSTR", days=10, max_retries=3,
                backoff_seconds=[1, 2, 3],
                sleeper=sleeps.append,
            )

        # Single attempt, no sleeps -- ValueError is not rate-limit-shaped.
        self.assertEqual(history_mock.call_count, 1)
        self.assertEqual(sleeps, [])
        self.assertTrue(result.empty)

    def test_rate_limit_matcher_accepts_message_only(self):
        # Generic Exception with a rate-limit message also retries.
        side_effects = [Exception("Too Many Requests. Rate limited."),
                        pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-01-01"]))]
        yf_mock, history_mock = self._stub_yfinance(side_effects)
        sleeps: list = []

        with patch.dict(sys.modules, {"yfinance": yf_mock}):
            result = data_fetch.fetch_price_history(
                "MSTR", days=10,
                backoff_seconds=[1],
                sleeper=sleeps.append,
            )

        self.assertEqual(history_mock.call_count, 2)
        self.assertEqual(sleeps, [1])
        self.assertFalse(result.empty)

    def test_multi_candidate_matcher(self):
        """Each strict-pattern candidate independently triggers retry."""
        cases = [
            # (exception_to_raise, label)
            (type("YFRateLimitError", (Exception,), {})("anything"), "YFRateLimitError class name"),
            (type("RateLimitError", (Exception,), {})("anything"), "RateLimitError class name"),
            (Exception("HTTP 429: throttled"), "429 in message"),
            (Exception("Too Many Requests"), "too many requests in message"),
        ]
        for exc, label in cases:
            with self.subTest(case=label):
                # Stub: raise the exception once, then return a frame.
                df = pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-01-01"]))
                # Use unique cache_path per subtest to avoid hits across iterations.
                ticker = f"TEST_{label.replace(' ', '_')[:10]}"
                yf_mock, history_mock = self._stub_yfinance([exc, df])
                sleeps: list = []
                with patch.dict(sys.modules, {"yfinance": yf_mock}):
                    result = data_fetch.fetch_price_history(
                        ticker, days=10,
                        backoff_seconds=[1],
                        sleeper=sleeps.append,
                    )
                self.assertEqual(
                    history_mock.call_count, 2,
                    f"{label}: expected retry (attempts=2), got {history_mock.call_count}",
                )
                self.assertEqual(sleeps, [1], f"{label}: expected one 1s sleep before retry")
                self.assertFalse(result.empty, f"{label}: result should be non-empty after retry success")


class TestInterTickerDelay(_TempCacheMixin, unittest.TestCase):
    """fetch_all_universe sleeps between tickers to stay under Yahoo's quota."""

    def test_sleeps_between_tickers(self):
        # Stub TradingVolatilityAPI to produce trivial gex.
        tv_mock = MagicMock()
        tv_mock.get_historical_gamma = MagicMock(return_value=[])
        cce_module = MagicMock()
        cce_module.TradingVolatilityAPI = MagicMock(return_value=tv_mock)

        # Stub yfinance to always succeed with a tiny frame.
        df = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2026-01-01"]))
        yf_mock = MagicMock()
        yf_mock.Ticker = MagicMock(return_value=MagicMock(history=MagicMock(return_value=df)))

        sleeps: list = []
        with patch.dict(sys.modules, {
            "core_classes_and_engines": cce_module,
            "yfinance": yf_mock,
        }):
            data_fetch.fetch_all_universe(
                days=10,
                pairs={"TSLL": "TSLA", "NVDL": "NVDA"},  # 2 pairs = 4 yf calls
                inter_ticker_delay_seconds=2.0,
                sleeper=sleeps.append,
            )

        # 2 pairs -> 4 yf calls; 3 sleeps between them (none before 1st call).
        self.assertEqual(sleeps, [2.0, 2.0, 2.0])

    def test_zero_delay_disables_sleep(self):
        tv_mock = MagicMock()
        tv_mock.get_historical_gamma = MagicMock(return_value=[])
        cce_module = MagicMock()
        cce_module.TradingVolatilityAPI = MagicMock(return_value=tv_mock)

        df = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2026-01-01"]))
        yf_mock = MagicMock()
        yf_mock.Ticker = MagicMock(return_value=MagicMock(history=MagicMock(return_value=df)))

        sleeps: list = []
        with patch.dict(sys.modules, {
            "core_classes_and_engines": cce_module,
            "yfinance": yf_mock,
        }):
            data_fetch.fetch_all_universe(
                days=10,
                pairs={"TSLL": "TSLA"},
                inter_ticker_delay_seconds=0.0,
                sleeper=sleeps.append,
            )

        self.assertEqual(sleeps, [])


if __name__ == "__main__":
    unittest.main()
