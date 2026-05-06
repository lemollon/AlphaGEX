import pytest
from backtest.directional_1dte.signals import Signal, generate_signal
from backtest.directional_1dte.config import SOLOMON


def walls(call_wall, put_wall, spot):
    return {"call_wall": call_wall, "put_wall": put_wall, "spot": spot}


class TestVixGate:
    def test_skip_when_vix_missing(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), spot=505, vix=None, config=solomon)
        assert sig is None
        assert reason == "NO_VIX_DATA"

    def test_skip_when_vix_below_min(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), 505, vix=10.0, config=solomon)
        assert sig is None
        assert reason == "VIX_OUT_OF_RANGE"

    def test_skip_when_vix_above_max(self, solomon):
        sig, reason = generate_signal(walls(510, 500, 505), 505, vix=40.0, config=solomon)
        assert sig is None
        assert reason == "VIX_OUT_OF_RANGE"


class TestWallProximity:
    def test_bullish_when_within_filter_of_put_wall(self, solomon):
        # spot 500, put_wall 498 -> 0.4% away (< 1%)
        sig, reason = generate_signal(walls(550, 498, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"
        assert sig.spread_type == "BULL_CALL"

    def test_bearish_when_within_filter_of_call_wall(self, solomon):
        # spot 500, call_wall 502 -> 0.4% away
        sig, reason = generate_signal(walls(502, 450, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BEARISH"
        assert sig.spread_type == "BEAR_PUT"

    def test_skip_when_neither_wall_in_range(self, solomon):
        # spot 500, walls 480 and 520 -> 4% away each
        sig, reason = generate_signal(walls(520, 480, 500), 500, vix=18.0, config=solomon)
        assert sig is None
        assert reason == "NOT_NEAR_WALL"


class TestTieBreak:
    def test_picks_closer_wall_in_dollars_when_both_within_filter(self, solomon):
        # spot 500. put_wall 499 ($1 away). call_wall 503 ($3 away). Both within 1%.
        sig, reason = generate_signal(walls(503, 499, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"  # closer wall = put_wall

    def test_bullish_wins_exact_dollar_tie(self, solomon):
        # spot 500. put_wall 498.5, call_wall 501.5. Both $1.50 away, both within 1%.
        sig, reason = generate_signal(walls(501.5, 498.5, 500), 500, vix=18.0, config=solomon)
        assert reason is None
        assert sig.direction == "BULLISH"


class TestMissingWalls:
    def test_skip_when_walls_dict_is_none(self, solomon):
        sig, reason = generate_signal(None, 500, 18.0, solomon)
        assert sig is None
        assert reason == "NO_WALLS_FOUND"

    def test_skip_when_call_wall_missing(self, solomon):
        sig, reason = generate_signal({"put_wall": 498, "call_wall": None, "spot": 500}, 500, 18.0, solomon)
        assert sig is None
        assert reason == "NO_WALLS_FOUND"
