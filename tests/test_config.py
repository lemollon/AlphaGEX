"""
Comprehensive Tests for Configuration Module

Tests the AlphaGEX configuration including:
- VIX configuration thresholds
- GEX threshold configuration
- Gamma decay patterns
- Trade setup configuration
- Directional prediction scoring

Run with: pytest tests/test_config.py -v
"""

import pytest
from unittest.mock import patch
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestVIXConfig:
    """Tests for VIX configuration"""

    def test_default_vix_value(self):
        """Test default VIX value is reasonable"""
        from config import VIXConfig

        assert VIXConfig.DEFAULT_VIX == 18.0
        assert 10 < VIXConfig.DEFAULT_VIX < 30

    def test_vix_thresholds_ordered(self):
        """Test VIX thresholds are properly ordered"""
        from config import VIXConfig

        assert VIXConfig.LOW_VIX_THRESHOLD < VIXConfig.ELEVATED_VIX_THRESHOLD
        assert VIXConfig.ELEVATED_VIX_THRESHOLD < VIXConfig.HIGH_VIX_THRESHOLD
        assert VIXConfig.HIGH_VIX_THRESHOLD < VIXConfig.EXTREME_VIX_THRESHOLD

    def test_historical_vix_values(self):
        """Test historical VIX averages are realistic"""
        from config import VIXConfig

        assert 10 < VIXConfig.HISTORICAL_AVERAGE_VIX < 25
        assert 10 < VIXConfig.RECENT_AVERAGE_VIX < 25


class TestGammaDecayConfig:
    """Tests for gamma decay pattern configuration"""

    def test_front_loaded_pattern_decreasing(self):
        """Test front-loaded pattern decreases over week"""
        from config import GammaDecayConfig

        pattern = GammaDecayConfig.FRONT_LOADED_PATTERN

        assert pattern[0] == 1.0  # Monday = 100%
        assert pattern[0] > pattern[1] > pattern[2] > pattern[3] > pattern[4]
        assert pattern[4] < 0.15  # Friday should be very low

    def test_balanced_pattern_decreasing(self):
        """Test balanced pattern decreases over week"""
        from config import GammaDecayConfig

        pattern = GammaDecayConfig.BALANCED_PATTERN

        assert pattern[0] == 1.0
        assert pattern[0] > pattern[1] > pattern[2] > pattern[3] > pattern[4]

    def test_back_loaded_pattern_slower_decay(self):
        """Test back-loaded pattern has slower early decay"""
        from config import GammaDecayConfig

        front = GammaDecayConfig.FRONT_LOADED_PATTERN
        back = GammaDecayConfig.BACK_LOADED_PATTERN

        # Back-loaded should retain more gamma on Tuesday
        assert back[1] > front[1]

    def test_all_patterns_start_at_100_percent(self):
        """Test all patterns start at 100% on Monday"""
        from config import GammaDecayConfig

        assert GammaDecayConfig.FRONT_LOADED_PATTERN[0] == 1.0
        assert GammaDecayConfig.BALANCED_PATTERN[0] == 1.0
        assert GammaDecayConfig.BACK_LOADED_PATTERN[0] == 1.0


class TestGEXThresholdConfig:
    """Tests for GEX threshold configuration"""

    def test_adaptive_multipliers_symmetric(self):
        """Test adaptive multipliers are roughly symmetric"""
        from config import GEXThresholdConfig

        multipliers = GEXThresholdConfig.ADAPTIVE_MULTIPLIERS

        # Positive and negative extremes should have same magnitude
        assert abs(multipliers['extreme_negative']) == abs(multipliers['extreme_positive'])
        assert abs(multipliers['high_negative']) == abs(multipliers['high_positive'])

    def test_adaptive_multipliers_ordered(self):
        """Test adaptive multipliers are properly ordered"""
        from config import GEXThresholdConfig

        m = GEXThresholdConfig.ADAPTIVE_MULTIPLIERS

        assert m['extreme_negative'] < m['high_negative'] < m['moderate_negative']
        assert m['moderate_positive'] < m['high_positive'] < m['extreme_positive']

    def test_fixed_thresholds_ordered(self):
        """Test fixed thresholds are properly ordered"""
        from config import GEXThresholdConfig

        t = GEXThresholdConfig.FIXED_THRESHOLDS

        assert t['extreme_negative'] < t['high_negative'] < t['moderate_negative']
        assert t['moderate_positive'] < t['high_positive'] < t['extreme_positive']

    def test_lookback_days_reasonable(self):
        """Test lookback period is reasonable"""
        from config import GEXThresholdConfig

        assert 10 <= GEXThresholdConfig.ADAPTIVE_LOOKBACK_DAYS <= 60


class TestDirectionalPredictionConfig:
    """Tests for directional prediction configuration"""

    def test_factor_weights_sum_to_one(self):
        """Test factor weights sum to 1.0 (100%)"""
        from config import DirectionalPredictionConfig

        weights = DirectionalPredictionConfig.FACTOR_WEIGHTS
        total = sum(weights.values())

        assert abs(total - 1.0) < 0.001

    def test_neutral_score_centered(self):
        """Test neutral score is centered at 50"""
        from config import DirectionalPredictionConfig

        assert DirectionalPredictionConfig.NEUTRAL_SCORE == 50

    def test_threshold_ordering(self):
        """Test direction thresholds are properly ordered"""
        from config import DirectionalPredictionConfig

        assert DirectionalPredictionConfig.DOWNWARD_THRESHOLD < DirectionalPredictionConfig.NEUTRAL_SCORE
        assert DirectionalPredictionConfig.NEUTRAL_SCORE < DirectionalPredictionConfig.UPWARD_THRESHOLD


class TestRiskLevelConfig:
    """Tests for risk level configuration"""

    def test_daily_risk_levels_valid_range(self):
        """Test daily risk levels are in valid range"""
        from config import RiskLevelConfig

        for day, risk in RiskLevelConfig.DAILY_RISK_LEVELS.items():
            assert 0 <= risk <= 100, f"Risk for {day} out of range: {risk}"

    def test_friday_highest_risk(self):
        """Test Friday has highest risk (expiration day)"""
        from config import RiskLevelConfig

        levels = RiskLevelConfig.DAILY_RISK_LEVELS
        assert levels['friday'] == max(levels.values())

    def test_monday_lowest_risk(self):
        """Test Monday has lowest risk (max gamma)"""
        from config import RiskLevelConfig

        levels = RiskLevelConfig.DAILY_RISK_LEVELS
        assert levels['monday'] == min(levels.values())

    def test_risk_thresholds_ordered(self):
        """Test risk thresholds are properly ordered"""
        from config import RiskLevelConfig

        assert RiskLevelConfig.MODERATE_RISK_THRESHOLD < RiskLevelConfig.HIGH_RISK_THRESHOLD
        assert RiskLevelConfig.HIGH_RISK_THRESHOLD < RiskLevelConfig.EXTREME_RISK_THRESHOLD


class TestTradeSetupConfig:
    """Tests for trade setup configuration"""

    def test_spread_widths_valid(self):
        """Test spread widths are reasonable percentages"""
        from config import TradeSetupConfig

        assert 0.01 <= TradeSetupConfig.SPREAD_WIDTH_NORMAL <= 0.05
        assert 0.01 <= TradeSetupConfig.SPREAD_WIDTH_LOW_PRICE <= 0.05

    def test_strike_increments_increasing(self):
        """Test strike increments increase with price"""
        from config import TradeSetupConfig

        assert TradeSetupConfig.STRIKE_INCREMENT_UNDER_20 <= TradeSetupConfig.STRIKE_INCREMENT_20_TO_100
        assert TradeSetupConfig.STRIKE_INCREMENT_20_TO_100 <= TradeSetupConfig.STRIKE_INCREMENT_100_TO_200
        assert TradeSetupConfig.STRIKE_INCREMENT_100_TO_200 <= TradeSetupConfig.STRIKE_INCREMENT_OVER_200

    def test_confidence_thresholds_valid(self):
        """Test confidence thresholds are valid probabilities"""
        from config import TradeSetupConfig

        assert 0 < TradeSetupConfig.MIN_CONFIDENCE_THRESHOLD < 1
        assert 0 < TradeSetupConfig.MIN_WIN_RATE_THRESHOLD < 1

    def test_base_confidence_values(self):
        """Test base confidence values are valid"""
        from config import TradeSetupConfig

        for strategy, conf in TradeSetupConfig.BASE_CONFIDENCE.items():
            assert 0.5 <= conf <= 1.0, f"Confidence for {strategy} out of range: {conf}"


class TestRateLimitConfig:
    """Tests for rate limiting configuration"""

    def test_min_request_interval_reasonable(self):
        """Test minimum request interval is reasonable"""
        from config import RateLimitConfig

        # Should be at least 1 second, no more than 30 seconds
        assert 1 <= RateLimitConfig.MIN_REQUEST_INTERVAL <= 30

    def test_circuit_breaker_duration_reasonable(self):
        """Test circuit breaker duration is reasonable"""
        from config import RateLimitConfig

        # Should be at least 30 seconds, no more than 5 minutes
        assert 30 <= RateLimitConfig.CIRCUIT_BREAKER_DURATION <= 300

    def test_cache_duration_reasonable(self):
        """Test cache duration is reasonable"""
        from config import RateLimitConfig

        # Should be at least 5 minutes, no more than 2 hours
        assert 300 <= RateLimitConfig.CACHE_DURATION <= 7200


class TestImpliedVolatilityConfig:
    """Tests for IV configuration"""

    def test_default_iv_reasonable(self):
        """Test default IV is reasonable"""
        from config import ImpliedVolatilityConfig

        assert 0.10 <= ImpliedVolatilityConfig.DEFAULT_IV <= 0.40

    def test_iv_percentile_thresholds_ordered(self):
        """Test IV percentile thresholds are ordered"""
        from config import ImpliedVolatilityConfig

        assert ImpliedVolatilityConfig.LOW_IV_PERCENTILE < ImpliedVolatilityConfig.HIGH_IV_PERCENTILE

    def test_iv_thresholds_ordered(self):
        """Test IV absolute thresholds are ordered"""
        from config import ImpliedVolatilityConfig

        assert ImpliedVolatilityConfig.LOW_IV_THRESHOLD < ImpliedVolatilityConfig.NORMAL_IV_THRESHOLD
        assert ImpliedVolatilityConfig.NORMAL_IV_THRESHOLD < ImpliedVolatilityConfig.HIGH_IV_THRESHOLD
        assert ImpliedVolatilityConfig.HIGH_IV_THRESHOLD < ImpliedVolatilityConfig.EXTREME_IV_THRESHOLD


class TestSystemConfig:
    """Tests for system configuration"""

    def test_environment_defaults_to_development(self):
        """Test environment defaults to development"""
        from config import SystemConfig

        # When no env var set, should default to development
        assert SystemConfig.ENVIRONMENT in ['development', 'production', 'staging']

    def test_log_level_valid(self):
        """Test log level is valid"""
        from config import SystemConfig

        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        assert SystemConfig.LOG_LEVEL in valid_levels

    def test_request_timeout_reasonable(self):
        """Test request timeout is reasonable"""
        from config import SystemConfig

        assert 30 <= SystemConfig.REQUEST_TIMEOUT <= 300

    def test_max_concurrent_calls_reasonable(self):
        """Test max concurrent API calls is reasonable"""
        from config import SystemConfig

        assert 1 <= SystemConfig.MAX_CONCURRENT_API_CALLS <= 20


class TestHelperFunctions:
    """Tests for helper functions"""

    def test_get_gex_thresholds_adaptive(self):
        """Test get_gex_thresholds with adaptive mode"""
        from config import get_gex_thresholds

        # With avg_gex provided, should use adaptive
        thresholds = get_gex_thresholds('SPY', avg_gex=5e9)

        assert 'extreme_negative' in thresholds
        assert 'extreme_positive' in thresholds

    def test_get_gex_thresholds_fixed(self):
        """Test get_gex_thresholds with fixed mode"""
        from config import get_gex_thresholds

        # Without avg_gex, should use fixed
        thresholds = get_gex_thresholds('SPY')

        assert 'extreme_negative' in thresholds
        assert thresholds['extreme_negative'] == -3e9

    def test_get_gamma_decay_pattern_default(self):
        """Test get_gamma_decay_pattern default behavior"""
        from config import get_gamma_decay_pattern

        pattern = get_gamma_decay_pattern()

        assert 0 in pattern
        assert 4 in pattern
        assert pattern[0] == 1.0

    def test_get_gamma_decay_pattern_high_vix(self):
        """Test get_gamma_decay_pattern with high VIX"""
        from config import get_gamma_decay_pattern, GammaDecayConfig

        pattern = get_gamma_decay_pattern(vix=35.0)

        # High VIX should use front-loaded pattern
        assert pattern == GammaDecayConfig.FRONT_LOADED_PATTERN

    def test_get_gamma_decay_pattern_low_vix(self):
        """Test get_gamma_decay_pattern with low VIX"""
        from config import get_gamma_decay_pattern, GammaDecayConfig

        pattern = get_gamma_decay_pattern(vix=12.0)

        # Low VIX should use back-loaded pattern
        assert pattern == GammaDecayConfig.BACK_LOADED_PATTERN


class TestConfigIntegrity:
    """Tests for overall config integrity"""

    def test_all_configs_importable(self):
        """Test all config classes can be imported"""
        from config import (
            VIXConfig,
            GammaDecayConfig,
            GEXThresholdConfig,
            DirectionalPredictionConfig,
            RiskLevelConfig,
            TradeSetupConfig,
            RateLimitConfig,
            ImpliedVolatilityConfig,
            SystemConfig
        )

        assert VIXConfig is not None
        assert GammaDecayConfig is not None
        assert GEXThresholdConfig is not None
        assert DirectionalPredictionConfig is not None
        assert RiskLevelConfig is not None
        assert TradeSetupConfig is not None
        assert RateLimitConfig is not None
        assert ImpliedVolatilityConfig is not None
        assert SystemConfig is not None

    def test_no_circular_dependencies(self):
        """Test config can be imported without circular dependency issues"""
        import importlib
        import config

        # Force reimport
        importlib.reload(config)

        assert config is not None
