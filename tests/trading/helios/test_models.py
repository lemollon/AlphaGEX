from trading.helios.models import HeliosConfig, SpreadType, HeliosTradeSignal, SkipReason


def test_default_config_matches_spec():
    cfg = HeliosConfig()
    assert cfg.ticker == "SPY"
    assert cfg.wall_filter_pct == 1.0
    assert cfg.wall_concentration_threshold == 2.0
    assert cfg.wall_top_n == 3
    assert cfg.spread_width == 2
    assert cfg.min_vix == 15.0
    assert cfg.max_vix == 35.0
    assert cfg.profit_target_pct == 20.0
    assert cfg.stop_loss_pct == 50.0
    assert cfg.stop_loss_grace_minutes == 30
    assert cfg.eod_close_time_ct == "14:50"
    assert cfg.max_trades_per_day == 1
    assert cfg.monitor_poll_seconds == 15


def test_skip_signal_carries_reason():
    sig = HeliosTradeSignal.skip(SkipReason.NO_MAJOR_WALL, "no qualifying call wall")
    assert sig.action == "SKIP"
    assert sig.skip_reason == SkipReason.NO_MAJOR_WALL


def test_trade_signal_has_strikes():
    sig = HeliosTradeSignal.trade(
        spread_type=SpreadType.BULL_CALL,
        long_strike=500.0,
        short_strike=502.0,
    )
    assert sig.action == "TRADE"
    assert sig.spread_type == SpreadType.BULL_CALL
    assert sig.long_strike == 500.0
    assert sig.short_strike == 502.0
