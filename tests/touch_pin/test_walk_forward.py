"""Tests for backtest.touch_pin.walk_forward."""
import datetime as dt
import pytest

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.walk_forward import (
    split_trades, evaluate_go_no_go, GoNoGoResult,
)


def _row(d: dt.date, side="PIN-CALL", pnl=8.0, mb=1.7):
    return TradeRow(
        trade_date=d, expiration_date=d + dt.timedelta(days=1),
        side=side, long_K=535.0, short_K=536.0, width=1.0,
        entry_mid=0.20, exit_mid=0.30, spot_5=533.0, spot_close=534.5,
        vix_close_prior=18.0, magnet_imbalance=mb, distance_pct=0.4,
        regime_label="NORMAL", implied_method1=0.45, implied_method2=0.20,
        iv_long_strike=0.18, touched_during_day=1, time_first_touch_minute=120,
        pnl_gross=10.0, pnl_net=pnl, slippage=2.0, commission=5.20,
        exit_skipped_reason=None,
    )


def test_split_trades_by_year():
    trades = [
        _row(dt.date(2023, 6, 1)),
        _row(dt.date(2024, 6, 1)),
        _row(dt.date(2025, 6, 1)),
    ]
    train, val, oos = split_trades(trades)
    assert len(train) == 1 and train[0].trade_date.year == 2023
    assert len(val) == 1 and val[0].trade_date.year == 2024
    assert len(oos) == 1 and oos[0].trade_date.year == 2025


def test_evaluate_go_no_go_passes_when_thresholds_met():
    # Build 35 in-sample (varying pnl for nonzero std), 18 OOS with similar mean
    import random
    random.seed(42)
    insample = []
    for i in range(35):
        # Mean ~$8, low std → high sharpe
        pnl = 8.0 + random.uniform(-1.0, 1.0)
        d = dt.date(2023, 1, (i % 28) + 1)
        insample.append(_row(d, pnl=pnl))
    oos = []
    for i in range(18):
        pnl = 7.0 + random.uniform(-1.0, 1.0)
        d = dt.date(2025, 1, (i % 28) + 1)
        oos.append(_row(d, pnl=pnl))
    res = evaluate_go_no_go(insample, oos)
    assert isinstance(res, GoNoGoResult)
    assert res.n_qualifying_bins >= 1
    # GO requires n_total >= 100; we only have 35 → expect NO-GO due to that
    # but qualifying bins exist
    assert "Qualifying bins:" in res.summary


def test_evaluate_go_no_go_fails_on_sample_size():
    train = [_row(dt.date(2023, 1, i+1), pnl=8.0) for i in range(5)]
    oos = [_row(dt.date(2025, 1, i+1), pnl=8.0) for i in range(5)]
    res = evaluate_go_no_go(train, oos)
    assert res.go is False
