"""Tests for backtest.touch_pin.binning."""
import datetime as dt
import pytest

from backtest.touch_pin.engine import TradeRow
from backtest.touch_pin.binning import bin_trades, BinSummary, _magnet_bucket, _vix_bucket, _distance_bucket


def make_row(side="PIN-CALL", magnet_imb=1.5, vix=18.0, dist=0.4, regime="NORMAL", pnl=10.0):
    return TradeRow(
        trade_date=dt.date(2024, 6, 4), expiration_date=dt.date(2024, 6, 5),
        side=side, long_K=535.0, short_K=536.0, width=1.0,
        entry_mid=0.20, exit_mid=0.30, spot_5=533.0, spot_close=534.5,
        vix_close_prior=vix, magnet_imbalance=magnet_imb, distance_pct=dist,
        regime_label=regime, implied_method1=0.45, implied_method2=0.20,
        iv_long_strike=0.18, touched_during_day=1, time_first_touch_minute=120,
        pnl_gross=10.0, pnl_net=pnl, slippage=2.0, commission=5.20,
        exit_skipped_reason=None,
    )


def test_bin_trades_buckets_and_aggregates():
    trades = [make_row(magnet_imb=1.4, pnl=5.0) for _ in range(10)] + \
             [make_row(magnet_imb=1.7, pnl=8.0) for _ in range(20)]
    bins = bin_trades(trades)
    assert all(isinstance(b, BinSummary) for b in bins)
    matching = [b for b in bins if b.magnet_imb_bucket == "1.5-2.0"]
    assert len(matching) >= 1
    found = matching[0]
    assert found.n == 20
    assert found.mean_pnl == pytest.approx(8.0)


def test_bin_buckets_known_boundaries():
    assert _magnet_bucket(1.0) == "<1.2"
    assert _magnet_bucket(1.3) == "1.2-1.5"
    assert _magnet_bucket(1.7) == "1.5-2.0"
    assert _magnet_bucket(2.5) == ">2.0"
    assert _vix_bucket(12) == "<15"
    assert _vix_bucket(17) == "15-20"
    assert _vix_bucket(25) == "20-30"
    assert _vix_bucket(35) == ">30"
    assert _distance_bucket(0.2) == "<0.3%"
    assert _distance_bucket(0.5) == "0.3-0.6%"
    assert _distance_bucket(0.7) == ">0.6%"
