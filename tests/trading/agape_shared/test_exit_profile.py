from trading.agape_shared.exit_profile import ExitProfile, default_chop_profile, default_trend_profile


def test_exit_profile_round_trip_dict():
    p = ExitProfile(
        activation_pct=0.3, trail_distance_pct=0.15, profit_target_pct=1.0,
        mfe_giveback_pct=40.0, max_hold_hours=6, max_unrealized_loss_pct=1.5,
        emergency_stop_pct=5.0,
    )
    p2 = ExitProfile.from_dict(p.to_dict())
    assert p2 == p


def test_default_chop_profile_is_tighter_than_trend():
    chop = default_chop_profile()
    trend = default_trend_profile()
    assert chop.activation_pct < trend.activation_pct
    assert chop.trail_distance_pct < trend.trail_distance_pct
    assert chop.max_hold_hours < trend.max_hold_hours
    assert chop.max_unrealized_loss_pct < trend.max_unrealized_loss_pct
    # Chop has a hard target, trend doesn't
    assert chop.profit_target_pct > 0
    assert trend.profit_target_pct == 0
    # Chop closes giveback faster
    assert chop.mfe_giveback_pct < trend.mfe_giveback_pct


def test_from_dict_tolerates_unknown_keys():
    p = ExitProfile.from_dict({
        "activation_pct": 0.5, "trail_distance_pct": 0.3, "profit_target_pct": 0.0,
        "mfe_giveback_pct": 50, "max_hold_hours": 12, "max_unrealized_loss_pct": 2.0,
        "emergency_stop_pct": 5.0, "extra_unknown_key": "ignored",
    })
    assert p.activation_pct == 0.5
