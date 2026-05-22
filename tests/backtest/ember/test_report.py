# tests/backtest/ember/test_report.py
import datetime as dt
import csv
from backtest.ember.engine import TradeResult
from backtest.ember.report import summarize, write_trades_csv


def _tr(pnl, reason="PT", minute=10):
    return TradeResult(
        trade_date=dt.date(2024, 6, 3), policy="p", entry_minute=0, exit_minute=minute,
        exit_reason=reason, entry_credit=1.0, exit_cost=0.5, pnl=pnl, max_favorable=pnl, max_adverse=-1.0,
    )


def test_summarize_basic_stats():
    trades = [_tr(40), _tr(40), _tr(-60), _tr(40)]
    s = summarize(trades)
    assert s["n"] == 4
    assert s["win_rate"] == 75.0
    assert abs(s["ev_per_contract"] - 15.0) < 1e-9   # (40+40-60+40)/4
    assert abs(s["total_pnl"] - 60.0) < 1e-9
    assert s["max_drawdown"] >= 0.0


def test_summarize_empty():
    s = summarize([])
    assert s["n"] == 0
    assert s["win_rate"] == 0.0
    assert s["ev_per_contract"] == 0.0


def test_pct_eod_counts_eod_exits():
    s = summarize([_tr(10, reason="EOD"), _tr(10, reason="PT")])
    assert s["pct_eod"] == 50.0


def test_write_trades_csv(tmp_path):
    path = tmp_path / "trades.csv"
    write_trades_csv([_tr(40), _tr(-60)], str(path))
    rows = list(csv.DictReader(path.open()))
    assert len(rows) == 2
    assert rows[0]["exit_reason"] == "PT"
    assert "pnl" in rows[0]
