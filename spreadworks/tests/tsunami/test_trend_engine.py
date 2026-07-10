"""Unit tests for the TSUNAMI-TREND signal math (backtest-validated engine)."""
from __future__ import annotations

import math
import unittest
from unittest.mock import patch

from backend.bots.tsunami import trend_engine


def _closes(closes: list[float]) -> list[float]:
    return list(closes)


class AdjustedCloses(unittest.TestCase):
    """Regression for the 2026-07 NVDL phantom signal: history must come
    from a split-adjusted source, exclude today's partial bar (the live
    quote is appended by the caller), and fail safe to [] on any error."""

    def _fake_yf(self, index_dates, closes):
        import sys
        import types
        import pandas as pd
        hist = pd.DataFrame({"Close": closes}, index=pd.to_datetime(index_dates))
        fake = types.ModuleType("yfinance")
        fake.Ticker = lambda _t: types.SimpleNamespace(
            history=lambda **_kw: hist)
        return patch.dict(sys.modules, {"yfinance": fake})

    def test_excludes_todays_partial_bar_and_bad_closes(self):
        from datetime import date, timedelta
        today = date(2026, 7, 9)
        dates = [today - timedelta(days=3), today - timedelta(days=2),
                 today - timedelta(days=1), today]
        with self._fake_yf(dates, [10.0, 0.0, 12.0, 99.0]),              patch.object(trend_engine, "_today_market_date", return_value=today):
            out = trend_engine._adjusted_closes("NVDL")
        # today's 99.0 partial bar dropped, zero close dropped
        self.assertEqual(out, [10.0, 12.0])

    def test_fetch_failure_returns_empty(self):
        import sys
        import types
        fake = types.ModuleType("yfinance")

        def _boom(_t):
            raise RuntimeError("rate limited")
        fake.Ticker = _boom
        with patch.dict(sys.modules, {"yfinance": fake}):
            out = trend_engine._adjusted_closes("NVDL")
        self.assertEqual(out, [])


class SignalWeight(unittest.TestCase):
    def test_trend_off_below_ma_returns_zero(self):
        closes = [100.0] * 80  # flat history
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(closes)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": 90.0}):  # below the 100 MA
            w, diag = trend_engine._signal_weight("TSLL")
        self.assertEqual(w, 0.0)
        self.assertEqual(diag["trending"], False)
        self.assertEqual(diag["price"], 90.0)
        # ma50 includes the live quote as "today's close" in the MA window
        # (49 historical 100.0 closes + the 90.0 live quote) / 50.
        self.assertAlmostEqual(diag["ma50"], (49 * 100.0 + 90.0) / 50)

    def test_trend_on_returns_vol_scaled_weight(self):
        # gentle uptrend: last > MA, RV small but positive
        closes = [100.0 * (1.002 ** i) for i in range(80)]
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(closes)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": closes[-1] * 1.01}):
            w, diag = trend_engine._signal_weight("TSLL")
        self.assertIsNotNone(w)
        self.assertGreater(w, 0.0)
        # cap: never more than SLICE * W_CAP
        self.assertLessEqual(w, trend_engine.SLICE * trend_engine.W_CAP + 1e-9)
        self.assertEqual(diag["trending"], True)
        self.assertIsNotNone(diag["rv20"])

    def test_index_sleeve_uses_override_slice_not_default(self):
        # Same trend/vol inputs, different ticker -- TQQQ (overridden to
        # 0.15) must come out to exactly 0.15/0.40 of TSLL's (default
        # 0.40) weight, all else equal.
        closes = [100.0 * (1.002 ** i) for i in range(80)]
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(closes)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": closes[-1] * 1.01}):
            w_default, _ = trend_engine._signal_weight("TSLL")
            w_override, _ = trend_engine._signal_weight("TQQQ")
        self.assertAlmostEqual(
            w_override,
            w_default * (trend_engine.SLICE_OVERRIDE["TQQQ"] / trend_engine.SLICE))

    def test_high_vol_scales_down(self):
        # violent series -> RV >> target -> weight well under SLICE
        closes = [100.0 + (8.0 if i % 2 else -8.0) for i in range(80)]
        base = [100.0 + i * 0.5 for i in range(80)]  # keep last above MA
        mixed = [b + (4.0 if i % 2 else -4.0) for i, b in enumerate(base)]
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(mixed)), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": mixed[-1] + 10}):
            w, diag = trend_engine._signal_weight("TSLL")
        self.assertIsNotNone(w)
        self.assertLess(w, trend_engine.SLICE)

    def test_unadjusted_split_jump_returns_no_signal(self):
        # SMST 2024-11 regression: a >100% bar-to-bar jump (unadjusted
        # reverse split) must fail safe to no-signal, not a phantom trend.
        closes = [40.0] * 60 + [160.0] * 20  # 4x jump mid-history
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(closes)),              patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": 165.0}):
            w, diag = trend_engine._signal_weight("SMST")
        self.assertIsNone(w)
        self.assertIsNone(diag["trending"])

    def test_quote_vs_history_split_mismatch_returns_no_signal(self):
        # Split effective today: history pre-split, live quote post-split.
        closes = [10.0] * 80
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=_closes(closes)),              patch.object(trend_engine.tradier_client, "get_quote",
                          return_value={"last": 40.0}):  # 4x reverse split
            w, diag = trend_engine._signal_weight("NVDL")
        self.assertIsNone(w)

    def test_no_data_returns_none(self):
        with patch.object(trend_engine, "_adjusted_closes",
                          return_value=[]), \
             patch.object(trend_engine.tradier_client, "get_quote",
                          return_value=None):
            w, diag = trend_engine._signal_weight("TSLL")
        self.assertIsNone(w)
        self.assertIsNone(diag["price"])
        self.assertIsNone(diag["trending"])


class LogSignal(unittest.TestCase):
    """_log_signal() writes on an INDEPENDENT connection from whatever
    run_rebalance() is using -- a failure here must never abort or poison
    the trading transaction (Postgres aborts the whole transaction on any
    statement error until rollback, so sharing a connection would risk
    silently losing real trades if this diagnostic-only insert broke)."""

    def test_uses_independent_connection_not_the_caller_s(self):
        inserts = []

        class _Cur:
            def execute(self, sql, params=()):
                inserts.append((sql, params))
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        class _LogConn:
            def cursor(self):
                return _Cur()
            def commit(self):
                pass
            def rollback(self):
                pass
            def close(self):
                pass

        log_conn = _LogConn()
        with patch.object(trend_engine, "get_connection", return_value=log_conn) as mock_get:
            trend_engine._log_signal(
                "TSLL", trend_engine._diag(price=10.0, ma50=9.5, rv20=0.3, trending=True),
                0.4, 5, 3, "BUY", "trend on, w=0.40")
        mock_get.assert_called_once()  # opened its own connection
        self.assertEqual(len(inserts), 1)
        self.assertIn("tsunami_trend_signals", inserts[0][0])
        self.assertEqual(inserts[0][1], ("TSLL", 10.0, 9.5, 0.3, True, 0.4, 5, 3, "BUY", "trend on, w=0.40"))

    def test_connect_failure_is_swallowed_not_raised(self):
        with patch.object(trend_engine, "get_connection", side_effect=RuntimeError("db down")):
            trend_engine._log_signal("TSLL", trend_engine._diag(), None, 0, 0, "NO_QUOTE", "no quote")
        # no exception propagated -- that's the whole point of this test

    def test_insert_failure_rolls_back_and_does_not_raise(self):
        class _BadCur:
            def execute(self, sql, params=()):
                raise RuntimeError("insert failed")
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        rollback_called = []

        class _LogConn:
            def cursor(self):
                return _BadCur()
            def commit(self):
                raise AssertionError("commit should not be reached")
            def rollback(self):
                rollback_called.append(True)
            def close(self):
                pass

        with patch.object(trend_engine, "get_connection", return_value=_LogConn()):
            trend_engine._log_signal("TSLL", trend_engine._diag(), None, 0, 0, "NO_QUOTE", "no quote")
        self.assertEqual(rollback_called, [True])


class MarkIntradayEquity(unittest.TestCase):
    """mark_intraday_equity() must re-price the held book and write a
    snapshot WITHOUT touching cash/book/trades (no trading)."""

    def _fake_conn(self, cash_row, book_rows):
        fetch_queue = [cash_row, book_rows]
        inserts = []

        class _Cur:
            def execute(self, sql, params=()):
                if sql.strip().upper().startswith("INSERT"):
                    inserts.append((sql, params))
            def fetchone(self):
                return fetch_queue.pop(0)
            def fetchall(self):
                return fetch_queue.pop(0)
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False

        class _Conn:
            def cursor(self):
                return _Cur()
            def commit(self):
                pass
            def rollback(self):
                pass
            def close(self):
                pass

        return _Conn(), inserts

    def test_marks_book_and_inserts_one_snapshot_no_trading(self):
        conn, inserts = self._fake_conn(cash_row=(100.0,), book_rows=[("TSLL", 3)])
        with patch.object(trend_engine, "is_database_available", return_value=True), \
             patch.object(trend_engine, "get_connection", return_value=conn), \
             patch.object(trend_engine.tradier_client, "get_quote", return_value={"last": 10.0}):
            equity = trend_engine.mark_intraday_equity()

        self.assertAlmostEqual(equity, 100.0 + 3 * 10.0)
        self.assertEqual(len(inserts), 1)
        self.assertIn("tsunami_equity_snapshots", inserts[0][0])
        self.assertIn("PLATFORM", inserts[0][0])
        self.assertEqual(inserts[0][1], (trend_engine.START_CASH, 100.0 + 3 * 10.0 - trend_engine.START_CASH, 0, 1, 100.0 + 3 * 10.0))

    def test_returns_none_when_db_unavailable(self):
        with patch.object(trend_engine, "is_database_available", return_value=False):
            self.assertIsNone(trend_engine.mark_intraday_equity())

    def test_zero_quote_excluded_from_equity(self):
        conn, inserts = self._fake_conn(cash_row=(50.0,), book_rows=[("BITX", 2)])
        with patch.object(trend_engine, "is_database_available", return_value=True), \
             patch.object(trend_engine, "get_connection", return_value=conn), \
             patch.object(trend_engine.tradier_client, "get_quote", return_value=None):
            equity = trend_engine.mark_intraday_equity()

        self.assertAlmostEqual(equity, 50.0)  # unpriceable holding contributes $0, not crash


class Config(unittest.TestCase):
    def test_backtested_parameters(self):
        # These are the values the 2026-07-03 backtest validated. Changing
        # them invalidates the backtest — fail loudly.
        # SLICE recalibrated 0.40 -> 0.30 with the 2026-07-09 fractional-
        # share switch (whole-share rounding was the implicit deployment
        # governor; fractional at 0.40 over-deploys -- see engine comment).
        self.assertEqual(trend_engine.SLICE, 0.30)
        self.assertEqual(trend_engine.VOL_TGT, 0.35)
        self.assertEqual(trend_engine.MA_N, 50)
        self.assertEqual(trend_engine.RV_N, 20)
        self.assertEqual(trend_engine.START_CASH, 500.0)
        self.assertEqual([l for _, l in trend_engine.PAIRS],
                         ["TSLL", "AMDL", "NVDL", "CONL", "MSTU",
                          "BITX", "ETHU", "IONX", "UXRP", "SPXL", "TQQQ",
                          "SBIT", "ETHD", "SMST", "SPXS", "SQQQ"])

    def test_index_sleeve_slice_override(self):
        # Calibrated 2026-07-07 (dev/ironforge-data/tools/tsunami_bt/
        # run_live17_fix_bt.py sweep): these four are correlated substitutes
        # for beta already held via the single-name longs, so they run at a
        # discounted slice -- 0.375x the global default, rescaled with the
        # 2026-07-09 fractional switch (0.30 * 0.375 = 0.1125).
        for t in ("SPXL", "TQQQ", "SPXS", "SQQQ"):
            self.assertEqual(trend_engine.SLICE_OVERRIDE[t], 0.1125)
        # everything else still uses the global default (no entry here)
        for t in ("TSLL", "AMDL", "NVDL", "CONL", "MSTU", "BITX", "ETHU",
                  "IONX", "UXRP", "SBIT", "ETHD", "SMST"):
            self.assertNotIn(t, trend_engine.SLICE_OVERRIDE)

    def test_uvxy_dropped(self):
        self.assertNotIn("UVXY", [l for _, l in trend_engine.PAIRS])


if __name__ == "__main__":
    unittest.main()
