"""Tests for scripts/goliath_calibration.py partial-run resumption.

Specifically the per-week CSV partial-skip behavior added in the yfinance
hardening commit. If a previous run left some pairs already in the CSV,
re-running with --per-week-csv should preserve those rows and only compute
the missing pairs (e.g. after MSTR yfinance rate-limit incident).
"""
from __future__ import annotations

import csv
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# Load the orchestrator script as a module so we can call its private
# helpers directly. Avoids running main() and shelling out.
_SCRIPT_PATH = os.path.join(_REPO_ROOT, "scripts", "goliath_calibration.py")
_spec = importlib.util.spec_from_file_location("goliath_calibration", _SCRIPT_PATH)
goliath_calibration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(goliath_calibration)


class TestReadExistingCsvPairs(unittest.TestCase):
    def test_returns_empty_when_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nope.csv")
            rows, pairs = goliath_calibration._read_existing_csv_pairs(path)
        self.assertEqual(rows, [])
        self.assertEqual(pairs, set())

    def test_reads_existing_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "existing.csv")
            with open(path, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["pair", "underlying", "week_ending", "x"])
                w.writeheader()
                w.writerow({"pair": "TSLL", "underlying": "TSLA", "week_ending": "2026-01-09", "x": "1.0"})
                w.writerow({"pair": "NVDL", "underlying": "NVDA", "week_ending": "2026-01-09", "x": "2.0"})
                w.writerow({"pair": "TSLL", "underlying": "TSLA", "week_ending": "2026-01-16", "x": "1.5"})
            rows, pairs = goliath_calibration._read_existing_csv_pairs(path)
        self.assertEqual(len(rows), 3)
        self.assertEqual(pairs, {"TSLL", "NVDL"})

    def test_handles_corrupt_csv_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "garbage.csv")
            # Binary-ish garbage that csv.DictReader will choke on or empty-skip.
            Path(path).write_bytes(b"\x00\x01\x02not,a,csv\n")
            rows, pairs = goliath_calibration._read_existing_csv_pairs(path)
        # Either treats as empty (graceful) or returns whatever DictReader
        # could parse; either way no exception.
        self.assertIsInstance(rows, list)
        self.assertIsInstance(pairs, set)


def _make_price_df(values: list[float]) -> pd.DataFrame:
    """Build a daily price DataFrame long enough to satisfy _emit_per_week_csv."""
    n = max(len(values), 60)  # need ~60 days for weekly resample + 30d trailing window
    base = values + [values[-1]] * (n - len(values))
    idx = pd.date_range("2026-01-01", periods=n, freq="B")
    return pd.DataFrame({"Close": base}, index=idx)


def _full_price_history() -> dict:
    """Synthetic price_history covering all 5 LETF pairs from LETF_PAIRS."""
    history: dict = {}
    for letf, underlying in goliath_calibration.LETF_PAIRS.items():
        # Underlying: gentle uptrend, LETF: 2× moves.
        u_values = [100.0 + i * 0.3 for i in range(60)]
        l_values = [10.0 + i * 0.06 for i in range(60)]
        history[underlying] = _make_price_df(u_values)
        history[letf] = _make_price_df(l_values)
    return history


class TestPerWeekCsvPartialResume(unittest.TestCase):
    def test_full_run_writes_all_pairs(self):
        history = _full_price_history()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "per_week.csv")
            goliath_calibration._emit_per_week_csv(
                price_history=history, leverage=2.0, vol_window_days=30,
                output_path=out,
            )
            with open(out, newline="") as f:
                rows = list(csv.DictReader(f))
        pairs = {r["pair"] for r in rows}
        self.assertEqual(pairs, set(goliath_calibration.LETF_PAIRS.keys()))

    def test_resume_preserves_existing_pairs(self):
        history = _full_price_history()
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "per_week.csv")
            # Pretend a prior run got 4 pairs in (e.g. MSTU rate-limited).
            with open(out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=[
                    "pair", "underlying", "week_ending", "underlying_close",
                    "letf_close", "underlying_return", "letf_return",
                    "observed_drag", "predicted_drag", "drag_residual",
                    "trailing_sigma_annualized", "predicted_te", "observed_te_proxy",
                ])
                w.writeheader()
                marker = "PRESERVED-FROM-PRIOR-RUN"
                for letf in ["TSLL", "NVDL", "CONL", "AMDL"]:
                    w.writerow({"pair": letf, "underlying": "X",
                                "week_ending": marker, "underlying_close": "0",
                                "letf_close": "0", "underlying_return": "0",
                                "letf_return": "0", "observed_drag": "0",
                                "predicted_drag": "", "drag_residual": "",
                                "trailing_sigma_annualized": "", "predicted_te": "",
                                "observed_te_proxy": "0"})

            goliath_calibration._emit_per_week_csv(
                price_history=history, leverage=2.0, vol_window_days=30,
                output_path=out,
            )

            with open(out, newline="") as f:
                rows = list(csv.DictReader(f))

        pairs_in_file = {r["pair"] for r in rows}
        # All 5 pairs present after resume.
        self.assertEqual(pairs_in_file, set(goliath_calibration.LETF_PAIRS.keys()))

        # Original 4 pairs' rows preserved verbatim (marker still there).
        preserved_count = sum(1 for r in rows if r.get("week_ending") == "PRESERVED-FROM-PRIOR-RUN")
        self.assertEqual(preserved_count, 4)

        # MSTU was the missing pair — its rows should be freshly computed
        # (no marker, real week_ending dates).
        mstu_rows = [r for r in rows if r["pair"] == "MSTU"]
        self.assertGreater(len(mstu_rows), 0)
        for r in mstu_rows:
            self.assertNotEqual(r["week_ending"], "PRESERVED-FROM-PRIOR-RUN")


if __name__ == "__main__":
    unittest.main()
