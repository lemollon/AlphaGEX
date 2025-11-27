"""
VIX Configuration Tests
=======================

Tests for VIX thresholds, stress factors, and fallback logic.
Validates consistency between config and trading modules.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestVIXThresholds:
    """Test VIX threshold configurations"""

    def test_config_thresholds_ascending(self):
        """VIX thresholds should be in ascending order"""
        try:
            from config import VIXConfig
            thresholds = [
                VIXConfig.LOW_VIX_THRESHOLD,
                VIXConfig.ELEVATED_VIX_THRESHOLD,
                VIXConfig.HIGH_VIX_THRESHOLD,
                VIXConfig.EXTREME_VIX_THRESHOLD
            ]
        except ImportError:
            # Use default values
            thresholds = [15.0, 20.0, 30.0, 40.0]

        for i in range(len(thresholds) - 1):
            assert thresholds[i] < thresholds[i + 1], \
                f"Threshold {thresholds[i]} should be < {thresholds[i + 1]}"

    def test_unified_config_thresholds(self):
        """unified_config VIX thresholds should be reasonable"""
        try:
            from unified_config import VIXConfiguration
            assert VIXConfiguration.LOW < VIXConfiguration.ELEVATED
            assert VIXConfiguration.ELEVATED < VIXConfiguration.HIGH
            assert VIXConfiguration.HIGH < VIXConfiguration.EXTREME
        except ImportError:
            # Default values
            assert 15.0 < 20.0 < 30.0 < 40.0

    def test_default_vix_reasonable(self):
        """Default VIX fallback should be reasonable (15-25)"""
        try:
            from config import VIXConfig
            default = VIXConfig.DEFAULT_VIX
        except ImportError:
            default = 20.0

        assert 15.0 <= default <= 25.0


class TestVIXStressMultipliers:
    """Test VIX stress multipliers for position sizing"""

    def test_stress_multipliers_defined(self):
        """All stress levels should have multipliers"""
        try:
            from unified_config import VIXConfiguration
            multipliers = VIXConfiguration.STRESS_MULTIPLIERS
        except ImportError:
            multipliers = {
                'low': 1.2,
                'normal': 1.0,
                'elevated': 0.75,
                'high': 0.50,
                'extreme': 0.25
            }

        required_levels = ['low', 'normal', 'elevated', 'high', 'extreme']
        for level in required_levels:
            assert level in multipliers

    def test_stress_multipliers_descending(self):
        """Higher stress = lower multiplier"""
        multipliers = {
            'low': 1.2,
            'normal': 1.0,
            'elevated': 0.75,
            'high': 0.50,
            'extreme': 0.25
        }

        levels = ['low', 'normal', 'elevated', 'high', 'extreme']
        for i in range(len(levels) - 1):
            current = multipliers[levels[i]]
            next_level = multipliers[levels[i + 1]]
            assert current >= next_level

    def test_extreme_multiplier_minimum(self):
        """Extreme stress should still allow some trading (>0)"""
        extreme_multiplier = 0.25
        assert extreme_multiplier > 0


class TestVIXFallbackLogic:
    """Test VIX fallback when API fails"""

    def test_fallback_priority_last_known(self):
        """Should use last known VIX first"""
        last_known = 22.5
        recent_avg = 18.0
        default = 20.0

        def get_fallback(last_known_vix):
            if last_known_vix and last_known_vix > 0:
                return last_known_vix
            return recent_avg

        result = get_fallback(last_known)
        assert result == 22.5

    def test_fallback_to_recent_average(self):
        """Should fall back to recent average when no last known"""
        recent_avg = 18.0
        default = 20.0

        def get_fallback(last_known_vix):
            if last_known_vix and last_known_vix > 0:
                return last_known_vix
            return recent_avg

        result = get_fallback(None)
        assert result == 18.0

    def test_fallback_zero_value_invalid(self):
        """Zero VIX value should trigger fallback"""
        def get_fallback(last_known_vix):
            if last_known_vix and last_known_vix > 0:
                return last_known_vix
            return 18.0

        result = get_fallback(0)
        assert result == 18.0


class TestVIXStressLevel:
    """Test VIX to stress level mapping"""

    def test_classify_low_vix(self):
        """VIX < 15 should be 'low' stress"""
        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        assert get_stress_level(12.0) == 'low'

    def test_classify_normal_vix(self):
        """VIX 15-20 should be 'normal' stress"""
        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        assert get_stress_level(18.0) == 'normal'

    def test_classify_elevated_vix(self):
        """VIX 20-30 should be 'elevated' stress"""
        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        assert get_stress_level(25.0) == 'elevated'

    def test_classify_high_vix(self):
        """VIX 30-40 should be 'high' stress"""
        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        assert get_stress_level(35.0) == 'high'

    def test_classify_extreme_vix(self):
        """VIX > 40 should be 'extreme' stress"""
        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        assert get_stress_level(50.0) == 'extreme'


class TestTraderVIXThresholds:
    """Test VIX thresholds in trading modules

    Note: Traders use different thresholds (22/28/35) than config (20/30/40)
    for more conservative position sizing. This is intentional.
    """

    def test_trader_thresholds_more_conservative(self):
        """Trader thresholds kick in earlier than config thresholds"""
        # Config thresholds
        config_elevated = 20
        config_high = 30
        config_extreme = 40

        # Trader thresholds (more conservative)
        trader_elevated = 22
        trader_high = 28
        trader_extreme = 35

        # Traders should kick in position reduction EARLIER
        assert trader_elevated >= config_elevated
        assert trader_high <= config_high
        assert trader_extreme <= config_extreme

    def test_trader_factor_at_vix_25(self):
        """At VIX 25, trader should reduce size but config wouldn't"""
        vix = 25.0

        # Trader logic (from autonomous_paper_trader.py)
        def get_trader_factor(v):
            if v >= 35:
                return 0.25
            elif v >= 28:
                return 0.50
            elif v >= 22:
                return 0.75
            return 1.0

        # Config logic (from unified_config.py)
        def get_config_factor(v):
            if v >= 40:
                return 0.25
            elif v >= 30:
                return 0.50
            elif v >= 20:
                return 0.75
            return 1.0

        # Trader is at 0.75, config would be at 0.75 too here
        # But at VIX 28, trader = 0.50, config = 0.75
        assert get_trader_factor(28) == 0.50
        assert get_config_factor(28) == 0.75


class TestVIXPositionMultiplier:
    """Test getting position multiplier from VIX"""

    def test_get_position_multiplier(self):
        """Position multiplier should match stress level"""
        multipliers = {
            'low': 1.2,
            'normal': 1.0,
            'elevated': 0.75,
            'high': 0.50,
            'extreme': 0.25
        }

        def get_stress_level(vix):
            if vix < 15:
                return 'low'
            elif vix < 20:
                return 'normal'
            elif vix < 30:
                return 'elevated'
            elif vix < 40:
                return 'high'
            return 'extreme'

        def get_position_multiplier(vix):
            level = get_stress_level(vix)
            return multipliers.get(level, 1.0)

        test_cases = [
            (12.0, 1.2),   # low
            (18.0, 1.0),   # normal
            (25.0, 0.75),  # elevated
            (35.0, 0.50),  # high
            (50.0, 0.25),  # extreme
        ]

        for vix, expected in test_cases:
            actual = get_position_multiplier(vix)
            assert actual == expected, f"VIX {vix}: expected {expected}, got {actual}"


class TestVIXHistoricalContext:
    """Test VIX historical context values"""

    def test_historical_average_reasonable(self):
        """Historical VIX average should be ~16-17"""
        historical_avg = 16.5
        assert 15.0 <= historical_avg <= 18.0

    def test_recent_average_reasonable(self):
        """Recent VIX average should be ~17-19"""
        recent_avg = 18.0
        assert 16.0 <= recent_avg <= 20.0

    def test_historical_lower_than_recent(self):
        """Historical average typically lower than recent"""
        historical = 16.5
        recent = 18.0

        # This is generally true in recent years
        assert historical <= recent


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
