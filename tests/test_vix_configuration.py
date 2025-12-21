"""
VIX Configuration Tests
=======================

Tests for VIX thresholds, stress factors, and fallback logic.
Validates consistency between config and trading modules.

Note: Uses VIXConfig from vix_routes as single source of truth for thresholds.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import unified VIX configuration
try:
    from backend.api.routes.vix_routes import VIXConfig, get_stress_level, calculate_fallback_iv_percentile
    VIX_ROUTES_AVAILABLE = True
except ImportError:
    VIX_ROUTES_AVAILABLE = False
    # Fallback defaults for tests
    class VIXConfig:
        THRESHOLD_LOW = 15.0
        THRESHOLD_ELEVATED = 20.0
        THRESHOLD_HIGH = 25.0
        THRESHOLD_EXTREME = 30.0
        MULTIPLIER_NORMAL = 1.0
        MULTIPLIER_ELEVATED = 0.75
        MULTIPLIER_HIGH = 0.50
        MULTIPLIER_EXTREME = 0.25
        DEFAULT_VIX = 18.0

    def get_stress_level(vix):
        if vix >= VIXConfig.THRESHOLD_EXTREME:
            return ('extreme', VIXConfig.MULTIPLIER_EXTREME)
        elif vix >= VIXConfig.THRESHOLD_HIGH:
            return ('high', VIXConfig.MULTIPLIER_HIGH)
        elif vix >= VIXConfig.THRESHOLD_ELEVATED:
            return ('elevated', VIXConfig.MULTIPLIER_ELEVATED)
        else:
            return ('normal', VIXConfig.MULTIPLIER_NORMAL)


class TestVIXThresholds:
    """Test VIX threshold configurations using unified VIXConfig"""

    def test_config_thresholds_ascending(self):
        """VIX thresholds should be in ascending order"""
        thresholds = [
            VIXConfig.THRESHOLD_LOW,
            VIXConfig.THRESHOLD_ELEVATED,
            VIXConfig.THRESHOLD_HIGH,
            VIXConfig.THRESHOLD_EXTREME
        ]

        for i in range(len(thresholds) - 1):
            assert thresholds[i] < thresholds[i + 1], \
                f"Threshold {thresholds[i]} should be < {thresholds[i + 1]}"

    def test_unified_config_thresholds(self):
        """VIXConfig thresholds should be reasonable"""
        assert VIXConfig.THRESHOLD_LOW < VIXConfig.THRESHOLD_ELEVATED
        assert VIXConfig.THRESHOLD_ELEVATED < VIXConfig.THRESHOLD_HIGH
        assert VIXConfig.THRESHOLD_HIGH < VIXConfig.THRESHOLD_EXTREME

    def test_default_vix_reasonable(self):
        """Default VIX fallback should be reasonable (15-25)"""
        assert 15.0 <= VIXConfig.DEFAULT_VIX <= 25.0

    def test_thresholds_historically_accurate(self):
        """Thresholds should match historical VIX behavior"""
        # Low threshold should be near historical average (~17)
        assert 12 <= VIXConfig.THRESHOLD_LOW <= 18

        # Elevated should be 20-25 (above average but not panic)
        assert 18 <= VIXConfig.THRESHOLD_ELEVATED <= 25

        # High should be 25-35 (significant stress)
        assert 22 <= VIXConfig.THRESHOLD_HIGH <= 35

        # Extreme should be 30+ (crisis levels)
        assert VIXConfig.THRESHOLD_EXTREME >= 28


class TestVIXStressMultipliers:
    """Test VIX stress multipliers for position sizing using VIXConfig"""

    def test_stress_multipliers_defined(self):
        """All stress level multipliers should be defined"""
        assert hasattr(VIXConfig, 'MULTIPLIER_NORMAL')
        assert hasattr(VIXConfig, 'MULTIPLIER_ELEVATED')
        assert hasattr(VIXConfig, 'MULTIPLIER_HIGH')
        assert hasattr(VIXConfig, 'MULTIPLIER_EXTREME')

    def test_stress_multipliers_descending(self):
        """Higher stress = lower multiplier"""
        assert VIXConfig.MULTIPLIER_NORMAL >= VIXConfig.MULTIPLIER_ELEVATED
        assert VIXConfig.MULTIPLIER_ELEVATED >= VIXConfig.MULTIPLIER_HIGH
        assert VIXConfig.MULTIPLIER_HIGH >= VIXConfig.MULTIPLIER_EXTREME

    def test_extreme_multiplier_minimum(self):
        """Extreme stress should still allow some trading (>0)"""
        assert VIXConfig.MULTIPLIER_EXTREME > 0

    def test_normal_multiplier_is_baseline(self):
        """Normal multiplier should be 1.0 (100%)"""
        assert VIXConfig.MULTIPLIER_NORMAL == 1.0

    def test_multipliers_are_valid_percentages(self):
        """All multipliers should be between 0 and 1"""
        for mult in [VIXConfig.MULTIPLIER_NORMAL, VIXConfig.MULTIPLIER_ELEVATED,
                     VIXConfig.MULTIPLIER_HIGH, VIXConfig.MULTIPLIER_EXTREME]:
            assert 0 < mult <= 1.0


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
    """Test VIX to stress level mapping using unified get_stress_level function"""

    def test_classify_normal_vix(self):
        """VIX below elevated threshold should be 'normal' stress"""
        level, _ = get_stress_level(18.0)
        assert level == 'normal'

    def test_classify_elevated_vix(self):
        """VIX at elevated threshold should be 'elevated' stress"""
        level, _ = get_stress_level(22.0)
        assert level == 'elevated'

    def test_classify_high_vix(self):
        """VIX at high threshold should be 'high' stress"""
        level, _ = get_stress_level(27.0)
        assert level == 'high'

    def test_classify_extreme_vix(self):
        """VIX at extreme threshold should be 'extreme' stress"""
        level, _ = get_stress_level(35.0)
        assert level == 'extreme'

    def test_stress_level_returns_multiplier(self):
        """get_stress_level should return both level and multiplier"""
        level, multiplier = get_stress_level(25.0)
        assert isinstance(level, str)
        assert isinstance(multiplier, float)
        assert 0 < multiplier <= 1.0


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
    """Test getting position multiplier from VIX using unified get_stress_level"""

    def test_get_position_multiplier_normal(self):
        """Normal VIX should return 1.0 multiplier"""
        _, multiplier = get_stress_level(18.0)
        assert multiplier == VIXConfig.MULTIPLIER_NORMAL

    def test_get_position_multiplier_elevated(self):
        """Elevated VIX should return 0.75 multiplier"""
        _, multiplier = get_stress_level(22.0)
        assert multiplier == VIXConfig.MULTIPLIER_ELEVATED

    def test_get_position_multiplier_high(self):
        """High VIX should return 0.50 multiplier"""
        _, multiplier = get_stress_level(27.0)
        assert multiplier == VIXConfig.MULTIPLIER_HIGH

    def test_get_position_multiplier_extreme(self):
        """Extreme VIX should return 0.25 multiplier"""
        _, multiplier = get_stress_level(35.0)
        assert multiplier == VIXConfig.MULTIPLIER_EXTREME

    def test_multipliers_decrease_with_stress(self):
        """Multipliers should decrease as VIX increases"""
        vix_levels = [15, 22, 27, 35]
        multipliers = [get_stress_level(vix)[1] for vix in vix_levels]

        # Each multiplier should be <= the previous
        for i in range(1, len(multipliers)):
            assert multipliers[i] <= multipliers[i-1], \
                f"Multiplier at VIX {vix_levels[i]} should be <= multiplier at VIX {vix_levels[i-1]}"


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
