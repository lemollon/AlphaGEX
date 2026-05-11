import datetime as dt

from trading.helios.models import (
    HeliosConfig, SpreadType, HeliosTradeSignal, SkipReason,
    SetupType, DailyState, ExitReason, JoshuaConfig,
)


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


def test_setup_type_values():
    assert SetupType.WALL_FADE.value == "wall_fade"
    assert SetupType.WALL_BREAK.value == "wall_break"
    assert SetupType.FLIP_CROSS.value == "flip_cross"


def test_daily_state_default_unfired():
    state = DailyState(trade_date=dt.date(2026, 5, 11))
    assert state.wall_fade_fired is False
    assert state.wall_break_fired is False
    assert state.flip_cross_fired is False
    assert state.last_signal_minute is None


def test_daily_state_setup_fired_check():
    state = DailyState(trade_date=dt.date(2026, 5, 11), wall_fade_fired=True)
    assert state.is_fired(SetupType.WALL_FADE)
    assert not state.is_fired(SetupType.WALL_BREAK)
    assert not state.is_fired(SetupType.FLIP_CROSS)


def test_exit_reason_values():
    assert ExitReason.PT.value == "PT"
    assert ExitReason.SL.value == "SL"
    assert ExitReason.TIME_STOP.value == "TIME_STOP"
    assert ExitReason.DATA_FAILURE.value == "DATA_FAILURE"


def test_joshua_config_defaults():
    cfg = JoshuaConfig()
    assert cfg.ticker == "SPY"
    assert cfg.profit_target_pct == 20.0
    assert cfg.stop_loss_pct == 30.0
    assert cfg.eod_time_ct == "15:55"
    assert cfg.risk_per_trade_pct == 0.20
    assert cfg.buying_power_usage_pct == 0.85
    assert cfg.spread_width == 1
    assert cfg.gex_stale_max_seconds == 90
    assert cfg.poll_seconds == 60
    assert cfg.wall_fade_em_threshold == 0.30
    assert cfg.wall_break_em_threshold == 0.20
    assert cfg.flip_hysteresis_pct == 0.0015
    assert cfg.flip_buffer_minutes == 5
    assert cfg.max_trades_per_setup_per_day == 3


def test_daily_state_count_and_cap():
    state = DailyState(trade_date=dt.date(2026, 5, 11), wall_fade_count=2)
    assert state.count_for(SetupType.WALL_FADE) == 2
    assert state.count_for(SetupType.WALL_BREAK) == 0
    assert state.is_capped(SetupType.WALL_FADE, max_per_day=3) is False
    assert state.is_capped(SetupType.WALL_FADE, max_per_day=2) is True
    assert state.is_capped(SetupType.WALL_BREAK, max_per_day=1) is False
