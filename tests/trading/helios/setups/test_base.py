import pytest

from trading.helios.models import SetupType
from trading.helios.setups.base import SetupAction


def test_setup_action_call_vertical():
    a = SetupAction(
        setup=SetupType.WALL_FADE,
        direction="call",
        long_strike=500.0,
        short_strike=501.0,
        reason="test",
    )
    assert a.setup == SetupType.WALL_FADE
    assert a.direction == "call"
    assert a.long_strike == 500.0
    assert a.short_strike == 501.0


def test_setup_action_invalid_direction_raises():
    with pytest.raises(ValueError):
        SetupAction(
            setup=SetupType.WALL_FADE,
            direction="banana",
            long_strike=500.0,
            short_strike=501.0,
            reason="test",
        )
