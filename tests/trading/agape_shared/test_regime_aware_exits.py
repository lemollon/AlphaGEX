# tests/trading/agape_shared/test_regime_aware_exits.py
import pytest
from trading.agape_shared.exit_profile import ExitProfile
from trading.agape_shared.regime_aware_exits import (
    evaluate_exit, ExitDecision, ExitAction,
)


PROFILE_CHOP = ExitProfile(
    activation_pct=0.3, trail_distance_pct=0.15, profit_target_pct=1.0,
    mfe_giveback_pct=40.0, max_hold_hours=6, max_unrealized_loss_pct=1.5,
    emergency_stop_pct=5.0,
)


def _state(side="long", entry=100.0, current=100.0, hwm=100.0,
           open_age_hours=0.0, trailing_active=False, current_stop=None):
    return {
        "side": side, "entry_price": entry, "current_price": current,
        "high_water_mark": hwm, "open_age_hours": open_age_hours,
        "trailing_active": trailing_active, "current_stop": current_stop,
    }


def test_max_loss_fires_first():
    s = _state(current=98.0)  # -2% loss
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MAX_LOSS_")


def test_emergency_stop_fires_above_max_loss():
    # Profile has emergency at 5%, max_loss at 1.5%; -1.5% triggers MAX_LOSS,
    # which is the correct first hit (not emergency).
    s = _state(current=98.5)  # -1.5% loss exactly
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.reason.startswith("MAX_LOSS_")


def test_profit_target_fires_in_chop():
    s = _state(current=101.0, hwm=101.0)  # +1% profit
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("PROFIT_TARGET_")


def test_trail_stop_hit_fires_before_giveback():
    # Trail already armed at 100.5; current 100.4 → hit
    s = _state(current=100.4, hwm=100.7, trailing_active=True, current_stop=100.5)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("TRAIL_STOP")
    assert d.close_price == pytest.approx(100.5)


def test_mfe_giveback_fires_when_no_other_trigger():
    # MFE pushed to +0.8% (hwm=100.8), then current pulled back to 100.45
    # giveback_pct = 40% → giveback_floor = 100 + (100.8-100)*(1-0.4) = 100.48
    # current 100.45 < floor 100.48 → close.
    s = _state(current=100.45, hwm=100.8)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MFE_GIVEBACK_")


def test_mfe_giveback_skips_below_min_mfe():
    # MFE only +0.4% — below the 0.5% minimum, don't fire giveback even if
    # current <= floor.
    s = _state(current=100.05, hwm=100.4)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.NONE


def test_arms_trail_when_max_profit_crosses_activation():
    # hwm=100.4 → max_profit_pct = 0.4% < activation 0.3% — already past, should arm.
    # Simpler: hwm=100.5 (+0.5% > 0.3% activation), no trail yet.
    s = _state(current=100.4, hwm=100.5, trailing_active=False)
    d = evaluate_exit(s, PROFILE_CHOP)
    # No close — but the decision should signal arm-trail with stop at hwm - trail_dist
    assert d.action == ExitAction.ARM_TRAIL
    expected_stop = max(100.0, 100.5 - 100.0 * (0.15 / 100))
    assert d.new_stop == pytest.approx(expected_stop)


def test_max_hold_fires_when_no_close_yet():
    s = _state(current=100.2, hwm=100.2, open_age_hours=6.5)  # > 6h limit
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason == "MAX_HOLD_TIME"


def test_short_side_giveback():
    # Short entry 100, hwm down to 99.2 (MFE +0.8%), current bounced to 99.55
    # giveback_floor = 100 - 0.8 * (1 - 0.4) = 99.52
    # 99.55 > 99.52 → close (price has retraced through floor for a short).
    s = _state(side="short", entry=100.0, current=99.55, hwm=99.2)
    d = evaluate_exit(s, PROFILE_CHOP)
    assert d.action == ExitAction.CLOSE
    assert d.reason.startswith("MFE_GIVEBACK_")
