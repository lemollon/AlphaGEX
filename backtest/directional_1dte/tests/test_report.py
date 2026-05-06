import csv
import datetime as dt
import json

import pytest
from backtest.directional_1dte.config import SOLOMON
from backtest.directional_1dte.engine import BacktestResult, Trade, Skip, EquityPoint
from backtest.directional_1dte.report import write_results, summary_stats


def _trade(date, pnl, direction="BULLISH", debit=0.80, vix=18.0):
    return Trade(
        bot="solomon", entry_date=date, expiration_date=date,
        direction=direction, spread_type="BULL_CALL" if direction == "BULLISH" else "BEAR_PUT",
        spot_at_entry=500.0, long_strike=500.0, short_strike=502.0,
        entry_debit=debit, contracts=12, spot_at_expiry=503.0,
        payoff_per_share=2.0, realized_pnl=pnl, vix_at_entry=vix,
        call_wall=540.0, put_wall=499.0,
        long_bid=None, long_ask=None, short_bid=None, short_ask=None,
        expiry_not_t_plus_1=False,
    )


@pytest.fixture
def result():
    r = BacktestResult(bot="solomon", config=SOLOMON,
                       start=dt.date(2024, 1, 1), end=dt.date(2024, 1, 5),
                       starting_capital=100000.0)
    r.trades = [
        _trade(dt.date(2024, 1, 2), 100.0),
        _trade(dt.date(2024, 1, 3), -200.0, direction="BEARISH"),
        _trade(dt.date(2024, 1, 4), 50.0, vix=25.0),
    ]
    r.skips = [Skip("solomon", dt.date(2024, 1, 5), "NOT_NEAR_WALL")]
    r.equity = [EquityPoint(dt.date(2024, 1, 2), 100100.0),
                EquityPoint(dt.date(2024, 1, 3), 99900.0),
                EquityPoint(dt.date(2024, 1, 4), 99950.0)]
    return r


def test_summary_stats_basic(result):
    s = summary_stats(result)
    assert s["total_trades"] == 3
    assert s["total_skips"] == 1
    assert s["total_pnl"] == pytest.approx(-50.0)
    assert s["win_rate"] == pytest.approx(2/3)
    assert s["avg_win"] == pytest.approx(75.0)
    assert s["avg_loss"] == pytest.approx(-200.0)


def test_write_results_creates_all_files(result, tmp_path):
    out = tmp_path / "solomon"
    write_results(result, out)
    assert (out / "summary.json").exists()
    assert (out / "trades.csv").exists()
    assert (out / "skips.csv").exists()
    assert (out / "equity_curve.csv").exists()
    assert (out / "by_year.csv").exists()
    assert (out / "by_vix_bucket.csv").exists()
    assert (out / "by_direction.csv").exists()
    assert (out / "top_trades.csv").exists()
    assert (out / "worst_trades.csv").exists()
    assert (out / "run.json").exists()


def test_summary_json_is_valid(result, tmp_path):
    out = tmp_path / "solomon"
    write_results(result, out)
    payload = json.loads((out / "summary.json").read_text())
    assert payload["bot"] == "solomon"
    assert payload["total_trades"] == 3
    assert payload["total_pnl"] == pytest.approx(-50.0)


def test_by_vix_bucket_partitions_trades(result, tmp_path):
    out = tmp_path / "solomon"
    write_results(result, out)
    rows = list(csv.DictReader((out / "by_vix_bucket.csv").open()))
    bucket_counts = {r["bucket"]: int(r["trades"]) for r in rows}
    # vix 18, 18, 25 -> normal=2, elevated=1
    assert bucket_counts.get("normal_15_22", 0) == 2
    assert bucket_counts.get("elevated_22_28", 0) == 1
