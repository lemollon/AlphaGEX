"""
Unit tests for ember_routes.py — pure helpers only (no DB, no uvicorn).
"""

from backend.api.routes.ember_routes import _policy_from_params


def test_policy_from_params_maps_fields():
    class Body:  # duck-typed stand-in matching the Pydantic model's attributes
        profit_target_pct = 40.0
        stop_loss_mult = 1.0
        time_stop_minute = 385
        trail_activation_pct = None
        trail_giveback_pct = None
        min_hold_minutes = 5

    p = _policy_from_params(Body())
    assert p.profit_target_pct == 40.0
    assert p.stop_loss_mult == 1.0
    assert p.time_stop_minute == 385
    assert p.min_hold_minutes == 5


def test_policy_from_params_name_is_custom():
    class Body:
        profit_target_pct = 30.0
        stop_loss_mult = 0.5
        time_stop_minute = None
        trail_activation_pct = None
        trail_giveback_pct = None
        min_hold_minutes = 5

    p = _policy_from_params(Body())
    assert p.name == "custom"


def test_policy_from_params_trail_fields_passed():
    class Body:
        profit_target_pct = 50.0
        stop_loss_mult = 2.0
        time_stop_minute = 300
        trail_activation_pct = 20.0
        trail_giveback_pct = 5.0
        min_hold_minutes = 10

    p = _policy_from_params(Body())
    assert p.trail_activation_pct == 20.0
    assert p.trail_giveback_pct == 5.0
    assert p.min_hold_minutes == 10
