import datetime as dt
from backtest.blaze_gex_0dte.metrics import summarize, go_no_go, Summary

def _oc(setup, realized_pct, debit, date):
    from backtest.joshua_replay.engine import TradeOutcome
    return TradeOutcome(trade_date=date, setup=setup, direction="call",
                        entry_minute=10, exit_minute=20, debit=debit,
                        exit_reason="PT", realized_pct=realized_pct)

def test_summarize_computes_wr_ev_pf():
    ocs = [
        _oc("wall_fade", 20.0, 0.50, dt.date(2024,1,2)),
        _oc("wall_fade", -30.0, 0.50, dt.date(2024,1,3)),
        _oc("wall_fade", 20.0, 0.50, dt.date(2025,1,2)),
    ]
    s = summarize(ocs)["wall_fade"]
    assert s.trades == 3
    assert abs(s.win_rate - (2/3)) < 1e-9
    assert abs(s.total_pnl - (0.10 - 0.15 + 0.10)) < 1e-9
    assert abs(s.profit_factor - (0.20 / 0.15)) < 1e-6

def test_go_no_go_requires_positive_ev_and_pf():
    good = Summary(setup="x", trades=10, win_rate=0.5, ev_per_contract=2.0,
                   total_pnl=20.0, max_drawdown=-5.0, profit_factor=1.5,
                   pnl_by_year={2023: 1.0, 2024: 1.0, 2025: 1.0})
    bad = Summary(setup="y", trades=10, win_rate=0.5, ev_per_contract=2.0,
                  total_pnl=20.0, max_drawdown=-5.0, profit_factor=1.1,
                  pnl_by_year={2023: 1.0, 2024: -1.0})
    assert go_no_go(good) == "GO"
    assert go_no_go(bad) == "NO-GO"
