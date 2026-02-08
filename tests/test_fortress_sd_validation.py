"""
Test FORTRESS SD-based strike validation fix.

This test verifies that FORTRESS now correctly rejects GEX walls and Oracle strikes
that are less than 1.2 SD from spot, falling back to SD-based calculation.

The bug was that FORTRESS used percentage-based validation (0.5%-5%) which could
accept GEX walls at 0.5% (~0.5 SD) while the SD fallback uses 1.2 SD.
"""

import pytest
import math
from unittest.mock import MagicMock, patch


class TestARESStrikeValidation:
    """Test FORTRESS strike selection enforces minimum 1.2 SD."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock FORTRESS config."""
        config = MagicMock()
        config.sd_multiplier = 1.2
        config.spread_width = 2.0
        config.ticker = "SPY"
        return config

    @pytest.fixture
    def signal_generator(self, mock_config):
        """Create a SignalGenerator with mocked components."""
        with patch('trading.fortress_v2.signals.get_gex_calculator', return_value=None):
            with patch('trading.fortress_v2.signals.TRADIER_GEX_AVAILABLE', False):
                with patch('trading.fortress_v2.signals.ORACLE_AVAILABLE', False):
                    with patch('trading.fortress_v2.signals.ARES_ML_AVAILABLE', False):
                        from trading.fortress_v2.signals import SignalGenerator
                        return SignalGenerator(mock_config)

    def test_tight_gex_walls_rejected(self, signal_generator):
        """
        Test that GEX walls closer than 1.2 SD are rejected.

        Scenario:
        - Spot: $600
        - VIX: 15 → Expected Move = $600 * (15/100) / sqrt(252) = $5.67
        - 1.2 SD = $6.80
        - GEX Put Wall: $597 (only 0.5% = ~0.53 SD away) - TOO TIGHT
        - GEX Call Wall: $603 (only 0.5% = ~0.53 SD away) - TOO TIGHT

        Expected: Should REJECT GEX walls and use SD-based strikes instead.
        """
        spot_price = 600.0
        vix = 15.0
        expected_move = spot_price * (vix / 100) / math.sqrt(252)  # ~$5.67

        # GEX walls that are too tight (only 0.5% = ~0.53 SD)
        put_wall = 597.0  # 0.5% below spot
        call_wall = 603.0  # 0.5% above spot

        strikes = signal_generator.calculate_strikes(
            spot_price=spot_price,
            expected_move=expected_move,
            call_wall=call_wall,
            put_wall=put_wall,
        )

        # Should NOT use GEX walls because they're too tight
        assert strikes['using_gex'] is False, "GEX walls should be rejected (< 1.2 SD)"

        # Should fall back to SD-based calculation (1.2 SD)
        assert strikes['source'].startswith('SD'), f"Should use SD fallback, got {strikes['source']}"

        # Verify put strike is at least 1.2 SD below spot
        min_put_distance = 1.2 * expected_move
        actual_put_distance = spot_price - strikes['put_short']
        assert actual_put_distance >= min_put_distance - 1, (
            f"Put strike too close: {actual_put_distance:.2f} < {min_put_distance:.2f}"
        )

        # Verify call strike is at least 1.2 SD above spot
        actual_call_distance = strikes['call_short'] - spot_price
        assert actual_call_distance >= min_put_distance - 1, (
            f"Call strike too close: {actual_call_distance:.2f} < {min_put_distance:.2f}"
        )

    def test_wide_gex_walls_accepted(self, signal_generator):
        """
        Test that GEX walls >= 1.2 SD are accepted.

        Scenario:
        - Spot: $600
        - VIX: 15 → Expected Move = ~$5.67
        - 1.2 SD = $6.80
        - GEX Put Wall: $592 (1.33% = ~1.4 SD away) - VALID
        - GEX Call Wall: $608 (1.33% = ~1.4 SD away) - VALID
        """
        spot_price = 600.0
        vix = 15.0
        expected_move = spot_price * (vix / 100) / math.sqrt(252)  # ~$5.67

        # GEX walls that are wide enough (> 1.2 SD)
        put_wall = 592.0  # ~1.4 SD below
        call_wall = 608.0  # ~1.4 SD above

        strikes = signal_generator.calculate_strikes(
            spot_price=spot_price,
            expected_move=expected_move,
            call_wall=call_wall,
            put_wall=put_wall,
        )

        # Should use GEX walls because they're wide enough
        assert strikes['using_gex'] is True, "GEX walls should be accepted (>= 1.2 SD)"
        assert strikes['source'] == 'GEX', f"Should use GEX source, got {strikes['source']}"

    def test_sd_fallback_minimum_12_sd(self, signal_generator):
        """
        Test that SD fallback uses minimum 1.2 SD.
        """
        spot_price = 600.0
        vix = 15.0
        expected_move = spot_price * (vix / 100) / math.sqrt(252)  # ~$5.67

        # No GEX walls - should use SD fallback
        strikes = signal_generator.calculate_strikes(
            spot_price=spot_price,
            expected_move=expected_move,
            call_wall=0,
            put_wall=0,
        )

        # Should use SD-based calculation
        assert strikes['source'].startswith('SD'), f"Should use SD source, got {strikes['source']}"

        # Verify 1.2 SD minimum
        put_distance = spot_price - strikes['put_short']
        call_distance = strikes['call_short'] - spot_price
        min_distance = 1.2 * expected_move

        assert put_distance >= min_distance - 1, (
            f"Put SD fallback too tight: {put_distance:.2f} < {min_distance:.2f}"
        )
        assert call_distance >= min_distance - 1, (
            f"Call SD fallback too tight: {call_distance:.2f} < {min_distance:.2f}"
        )

    def test_low_vix_tight_walls_rejected(self, signal_generator):
        """
        Regression test: In low VIX environment, tight GEX walls
        must still be rejected.

        This was the actual bug - in low VIX, 0.5% from spot might
        only be 0.5 SD, but the old code accepted it because 0.5% >= 0.5%.
        """
        spot_price = 600.0
        vix = 12.0  # Low VIX
        expected_move = spot_price * (vix / 100) / math.sqrt(252)  # ~$4.53

        # 0.5% from spot = $3, but at VIX 12, 1.2 SD = ~$5.44
        # So $597/$603 walls (0.5% away) are only ~0.66 SD
        put_wall = 597.0
        call_wall = 603.0

        strikes = signal_generator.calculate_strikes(
            spot_price=spot_price,
            expected_move=expected_move,
            call_wall=call_wall,
            put_wall=put_wall,
        )

        # Must reject these tight walls
        assert strikes['using_gex'] is False, (
            "In low VIX, GEX walls at 0.5% (only ~0.66 SD) must be rejected"
        )

        # Verify strikes are actually wider than the rejected walls
        assert strikes['put_short'] < put_wall, (
            f"Put strike {strikes['put_short']} should be below rejected wall {put_wall}"
        )
        assert strikes['call_short'] > call_wall, (
            f"Call strike {strikes['call_short']} should be above rejected wall {call_wall}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
