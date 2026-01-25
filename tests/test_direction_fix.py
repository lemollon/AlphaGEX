"""
Tests for Direction Fix in PriceTrendTracker

These tests verify the fix that ensures wall proximity takes priority
over trend direction when price is near a GEX wall.

The bug was: Trend direction overrode wall proximity, causing wrong trades.
- Near PUT wall + trend BEARISH → incorrectly chose BEARISH (should be BULLISH)
- Near CALL wall + trend BULLISH → incorrectly chose BULLISH (should be BEARISH)

The fix: When within wall_filter_pct of a wall, wall determines direction.

Run with: pytest tests/test_direction_fix.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDirectionFixImport:
    """Test that PriceTrendTracker can be imported"""

    def test_import_price_trend_tracker(self):
        """Test that PriceTrendTracker can be imported"""
        from quant.price_trend_tracker import PriceTrendTracker
        assert PriceTrendTracker is not None

    def test_import_get_trend_tracker(self):
        """Test that get_trend_tracker function exists"""
        from quant.price_trend_tracker import get_trend_tracker
        assert get_trend_tracker is not None


class TestDirectionLogicFix:
    """
    Tests for the core direction logic fix.

    Key principle: Wall proximity MUST take priority when near a wall.
    - Near PUT wall → BULLISH (expect bounce off support)
    - Near CALL wall → BEARISH (expect rejection at resistance)
    """

    @pytest.fixture
    def tracker(self):
        """Get PriceTrendTracker instance"""
        from quant.price_trend_tracker import PriceTrendTracker
        return PriceTrendTracker.get_instance()

    @pytest.fixture
    def mock_wall_position_near_put(self):
        """Mock wall position - price near PUT wall"""
        mock = MagicMock()
        mock.dist_to_put_wall_pct = 0.5  # 0.5% from put wall (within 1% threshold)
        mock.dist_to_call_wall_pct = 4.5  # 4.5% from call wall (outside threshold)
        mock.position_in_range_pct = 10  # Lower 10% of range
        mock.nearest_wall = "PUT_WALL"
        mock.nearest_wall_distance_pct = 0.5
        return mock

    @pytest.fixture
    def mock_wall_position_near_call(self):
        """Mock wall position - price near CALL wall"""
        mock = MagicMock()
        mock.dist_to_put_wall_pct = 4.5  # 4.5% from put wall (outside threshold)
        mock.dist_to_call_wall_pct = 0.5  # 0.5% from call wall (within 1% threshold)
        mock.position_in_range_pct = 90  # Upper 90% of range
        mock.nearest_wall = "CALL_WALL"
        mock.nearest_wall_distance_pct = 0.5
        return mock

    @pytest.fixture
    def mock_wall_position_middle(self):
        """Mock wall position - price in middle, not near any wall"""
        mock = MagicMock()
        mock.dist_to_put_wall_pct = 2.5  # 2.5% from put wall (outside 1% threshold)
        mock.dist_to_call_wall_pct = 2.5  # 2.5% from call wall (outside 1% threshold)
        mock.position_in_range_pct = 50  # Middle of range
        mock.nearest_wall = "PUT_WALL"  # Slightly closer to put
        mock.nearest_wall_distance_pct = 2.5
        return mock

    @pytest.fixture
    def mock_trend_bearish(self):
        """Mock trend analysis - BEARISH trend"""
        mock = MagicMock()
        mock.derived_direction = "BEARISH"
        mock.derived_confidence = 0.60
        mock.reasoning = "Price falling, higher lows"
        from quant.price_trend_tracker import TrendDirection
        mock.direction = TrendDirection.DOWNTREND
        mock.strength = 0.7
        return mock

    @pytest.fixture
    def mock_trend_bullish(self):
        """Mock trend analysis - BULLISH trend"""
        mock = MagicMock()
        mock.derived_direction = "BULLISH"
        mock.derived_confidence = 0.60
        mock.reasoning = "Price rising, higher highs"
        from quant.price_trend_tracker import TrendDirection
        mock.direction = TrendDirection.UPTREND
        mock.strength = 0.7
        return mock

    def test_near_put_wall_returns_bullish_even_with_bearish_trend(
        self, tracker, mock_wall_position_near_put, mock_trend_bearish
    ):
        """
        THE CRITICAL FIX TEST

        When price is near PUT wall (support), direction MUST be BULLISH,
        regardless of what the trend says.

        Before fix: Trend BEARISH would override → wrong direction
        After fix: Wall proximity wins → correct BULLISH direction
        """
        with patch.object(tracker, 'analyze_trend', return_value=mock_trend_bearish):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_near_put):
                direction, confidence, reasoning, wall_filter_passed = \
                    tracker.get_neutral_regime_direction(
                        symbol="SPY",
                        spot_price=588.0,
                        call_wall=595.0,
                        put_wall=585.0,
                        wall_filter_pct=1.0  # 1% threshold
                    )

                # THE KEY ASSERTION
                assert direction == "BULLISH", \
                    f"Near PUT wall should be BULLISH, got {direction}"
                assert wall_filter_passed is True, \
                    "Wall filter should pass when within threshold"
                assert "put wall" in reasoning.lower(), \
                    f"Reasoning should mention put wall: {reasoning}"

    def test_near_call_wall_returns_bearish_even_with_bullish_trend(
        self, tracker, mock_wall_position_near_call, mock_trend_bullish
    ):
        """
        When price is near CALL wall (resistance), direction MUST be BEARISH,
        regardless of what the trend says.
        """
        with patch.object(tracker, 'analyze_trend', return_value=mock_trend_bullish):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_near_call):
                direction, confidence, reasoning, wall_filter_passed = \
                    tracker.get_neutral_regime_direction(
                        symbol="SPY",
                        spot_price=594.5,
                        call_wall=595.0,
                        put_wall=585.0,
                        wall_filter_pct=1.0
                    )

                assert direction == "BEARISH", \
                    f"Near CALL wall should be BEARISH, got {direction}"
                assert wall_filter_passed is True
                assert "call wall" in reasoning.lower()

    def test_middle_of_range_uses_trend(
        self, tracker, mock_wall_position_middle, mock_trend_bearish
    ):
        """
        When NOT near any wall, trend direction should be used.
        This ensures we didn't break the trend-following behavior.
        """
        with patch.object(tracker, 'analyze_trend', return_value=mock_trend_bearish):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_middle):
                direction, confidence, reasoning, wall_filter_passed = \
                    tracker.get_neutral_regime_direction(
                        symbol="SPY",
                        spot_price=590.0,
                        call_wall=595.0,
                        put_wall=585.0,
                        wall_filter_pct=1.0  # 1% threshold - neither wall is within
                    )

                # Middle of range, not near walls → should use trend
                assert direction == "BEARISH", \
                    f"Middle of range should use trend (BEARISH), got {direction}"
                assert wall_filter_passed is False, \
                    "Wall filter should NOT pass when not near wall"
                assert "trend" in reasoning.lower(), \
                    f"Reasoning should mention trend: {reasoning}"

    def test_wall_filter_passed_only_when_near_wall(
        self, tracker, mock_wall_position_near_put, mock_wall_position_middle
    ):
        """
        wall_filter_passed should only be True when within wall_filter_pct of a wall.
        """
        # Near wall - should pass
        with patch.object(tracker, 'analyze_trend', return_value=None):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_near_put):
                _, _, _, passed_near = tracker.get_neutral_regime_direction(
                    "SPY", 588.0, 595.0, 585.0, wall_filter_pct=1.0
                )
                assert passed_near is True

        # Middle - should not pass
        with patch.object(tracker, 'analyze_trend', return_value=None):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_middle):
                _, _, _, passed_middle = tracker.get_neutral_regime_direction(
                    "SPY", 590.0, 595.0, 585.0, wall_filter_pct=1.0
                )
                assert passed_middle is False

    def test_confidence_levels(
        self, tracker, mock_wall_position_near_put, mock_wall_position_middle
    ):
        """
        Confidence should be higher when wall filter passes (0.65)
        vs when using trend or general proximity (lower).
        """
        # Near wall - should have 0.65 confidence
        with patch.object(tracker, 'analyze_trend', return_value=None):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall_position_near_put):
                _, conf_near, _, _ = tracker.get_neutral_regime_direction(
                    "SPY", 588.0, 595.0, 585.0, wall_filter_pct=1.0
                )
                assert conf_near == 0.65, f"Wall proximity confidence should be 0.65, got {conf_near}"


class TestApacheBacktestScenarios:
    """
    Tests that reproduce Apache backtest scenarios.

    Apache used wall_filter_pct=1.0% and achieved 58% win rate.
    These tests verify the fix matches Apache's direction logic.
    """

    @pytest.fixture
    def tracker(self):
        from quant.price_trend_tracker import PriceTrendTracker
        return PriceTrendTracker.get_instance()

    def test_apache_scenario_price_falling_toward_put_wall(self, tracker):
        """
        Apache scenario: Price is falling toward put wall.

        Old behavior: Trend says BEARISH → wrong BEAR_PUT trade
        New behavior: Near put wall → correct BULL_CALL trade

        This was the PRIMARY BUG causing 17% win rate instead of 58%.
        """
        # Mock: Price at 588 falling toward put wall at 585 (0.51% away)
        mock_wall = MagicMock()
        mock_wall.dist_to_put_wall_pct = 0.51  # Within 1% threshold
        mock_wall.dist_to_call_wall_pct = 1.69
        mock_wall.position_in_range_pct = 23
        mock_wall.nearest_wall = "PUT_WALL"
        mock_wall.nearest_wall_distance_pct = 0.51

        # Mock: Trend is BEARISH (price falling)
        mock_trend = MagicMock()
        mock_trend.derived_direction = "BEARISH"
        mock_trend.derived_confidence = 0.65
        mock_trend.reasoning = "Price falling with momentum"
        from quant.price_trend_tracker import TrendDirection
        mock_trend.direction = TrendDirection.DOWNTREND

        with patch.object(tracker, 'analyze_trend', return_value=mock_trend):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall):
                direction, _, reasoning, wall_passed = tracker.get_neutral_regime_direction(
                    symbol="SPY",
                    spot_price=588.0,
                    call_wall=598.0,
                    put_wall=585.0,
                    wall_filter_pct=1.0  # Apache setting
                )

        # THE FIX: Should be BULLISH despite bearish trend
        assert direction == "BULLISH", \
            f"Apache scenario: Near put wall should be BULLISH (bounce), got {direction}"
        assert wall_passed is True


class TestEdgeCases:
    """Tests for edge cases and boundary conditions"""

    @pytest.fixture
    def tracker(self):
        from quant.price_trend_tracker import PriceTrendTracker
        return PriceTrendTracker.get_instance()

    def test_exactly_at_wall_filter_threshold(self, tracker):
        """Test when price is exactly at wall_filter_pct (boundary)"""
        mock_wall = MagicMock()
        mock_wall.dist_to_put_wall_pct = 1.0  # Exactly at 1% threshold
        mock_wall.dist_to_call_wall_pct = 4.0
        mock_wall.position_in_range_pct = 20
        mock_wall.nearest_wall = "PUT_WALL"
        mock_wall.nearest_wall_distance_pct = 1.0

        with patch.object(tracker, 'analyze_trend', return_value=None):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall):
                direction, _, _, wall_passed = tracker.get_neutral_regime_direction(
                    "SPY", 588.0, 598.0, 582.0, wall_filter_pct=1.0
                )

        # At exactly threshold should pass (<=)
        assert wall_passed is True
        assert direction == "BULLISH"

    def test_no_trend_analysis_available(self, tracker):
        """Test when trend analysis returns None"""
        mock_wall = MagicMock()
        mock_wall.dist_to_put_wall_pct = 2.0  # Outside threshold
        mock_wall.dist_to_call_wall_pct = 3.0
        mock_wall.position_in_range_pct = 40  # Lower-middle
        mock_wall.nearest_wall = "PUT_WALL"
        mock_wall.nearest_wall_distance_pct = 2.0

        with patch.object(tracker, 'analyze_trend', return_value=None):
            with patch.object(tracker, 'analyze_wall_position', return_value=mock_wall):
                direction, confidence, _, wall_passed = tracker.get_neutral_regime_direction(
                    "SPY", 590.0, 598.0, 582.0, wall_filter_pct=1.0
                )

        # Should fall back to position-based logic
        assert direction in ["BULLISH", "BEARISH", "FLAT"]
        assert wall_passed is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
