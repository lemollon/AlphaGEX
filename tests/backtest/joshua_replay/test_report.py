import datetime as dt

from backtest.joshua_replay.engine import TradeOutcome
from backtest.joshua_replay.report import build_report


def _t(date, setup, direction, debit, pct, reason):
    return TradeOutcome(
        trade_date=date, setup=setup, direction=direction,
        entry_minute=60, exit_minute=120, debit=debit,
        exit_reason=reason, realized_pct=pct,
    )


def test_report_aggregates_per_setup_metrics():
    trades = [
        _t(dt.date(2026, 5, 1), "wall_fade", "put", 0.50, 20.0, "PT"),
        _t(dt.date(2026, 5, 1), "wall_fade", "put", 0.50, -30.0, "SL"),
        _t(dt.date(2026, 5, 2), "wall_fade", "call", 0.50, 20.0, "PT"),
        _t(dt.date(2026, 5, 3), "wall_break", "call", 0.40, 20.0, "PT"),
    ]
    report = build_report(trades, start=dt.date(2026, 5, 1), end=dt.date(2026, 5, 3))
    assert "JOSHUA Replay Report" in report
    assert "wall_fade" in report
    assert "wall_break" in report
    # 3 of 4 wins -> 75%
    assert "75.0%" in report


def test_report_no_trades_emits_blank_verdict():
    report = build_report([], start=dt.date(2026, 5, 1), end=dt.date(2026, 5, 3))
    assert "No trades fired" in report
