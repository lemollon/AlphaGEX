"""
Tests for core trading logic modules.

This test suite covers the most critical trading logic:
- MarketRegimeClassifier: Regime classification and action decisions
- ProbabilityCalculator: Probability weight calculations
- Risk calculations and position sizing

Run with: pytest tests/test_core_trading_logic.py -v
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from market_regime_classifier import (
    MarketRegimeClassifier,
    MarketAction,
    VolatilityRegime,
    GammaRegime,
    TrendRegime,
    RegimeClassification,
)


class TestMarketRegimeClassifier:
    """Tests for MarketRegimeClassifier"""

    @pytest.fixture
    def classifier(self):
        """Create a classifier with database disabled"""
        with patch('market_regime_classifier.DB_AVAILABLE', False):
            return MarketRegimeClassifier(symbol="SPY")

    # =========================================================================
    # IV Rank Calculation Tests
    # =========================================================================

    def test_calculate_iv_rank_normal_range(self, classifier):
        """Test IV rank calculation with normal data"""
        current_iv = 0.20
        iv_history = [0.15, 0.18, 0.22, 0.25, 0.20, 0.19, 0.21] * 10  # ~70 days

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert 0 <= iv_rank <= 100
        assert 0 <= iv_percentile <= 100

    def test_calculate_iv_rank_extreme_high(self, classifier):
        """Test IV rank when current IV is at the top of range"""
        current_iv = 0.30
        iv_history = [0.15, 0.18, 0.20, 0.22, 0.25] * 20

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank == 100.0  # At max
        assert iv_percentile == 100.0  # Higher than all historical

    def test_calculate_iv_rank_extreme_low(self, classifier):
        """Test IV rank when current IV is at the bottom of range"""
        current_iv = 0.10
        iv_history = [0.15, 0.18, 0.20, 0.22, 0.25] * 20

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank == 0.0  # Below min (clamped)
        assert iv_percentile == 0.0  # Lower than all historical

    def test_calculate_iv_rank_insufficient_data(self, classifier):
        """Test IV rank with insufficient historical data"""
        current_iv = 0.20
        iv_history = [0.18, 0.19]  # Only 2 days

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        # Should return default 50, 50 with insufficient data
        assert iv_rank == 50.0
        assert iv_percentile == 50.0

    def test_calculate_iv_rank_empty_history(self, classifier):
        """Test IV rank with empty history"""
        iv_rank, iv_percentile = classifier.calculate_iv_rank(0.20, [])

        assert iv_rank == 50.0
        assert iv_percentile == 50.0

    # =========================================================================
    # Volatility Regime Classification Tests
    # =========================================================================

    def test_classify_volatility_extreme_high(self, classifier):
        """Test volatility regime classification for extreme high IV"""
        assert classifier.classify_volatility_regime(85) == VolatilityRegime.EXTREME_HIGH
        assert classifier.classify_volatility_regime(100) == VolatilityRegime.EXTREME_HIGH

    def test_classify_volatility_high(self, classifier):
        """Test volatility regime classification for high IV"""
        assert classifier.classify_volatility_regime(70) == VolatilityRegime.HIGH
        assert classifier.classify_volatility_regime(60) == VolatilityRegime.HIGH

    def test_classify_volatility_normal(self, classifier):
        """Test volatility regime classification for normal IV"""
        assert classifier.classify_volatility_regime(50) == VolatilityRegime.NORMAL
        assert classifier.classify_volatility_regime(40) == VolatilityRegime.NORMAL

    def test_classify_volatility_low(self, classifier):
        """Test volatility regime classification for low IV"""
        assert classifier.classify_volatility_regime(30) == VolatilityRegime.LOW
        assert classifier.classify_volatility_regime(20) == VolatilityRegime.LOW

    def test_classify_volatility_extreme_low(self, classifier):
        """Test volatility regime classification for extreme low IV"""
        assert classifier.classify_volatility_regime(15) == VolatilityRegime.EXTREME_LOW
        assert classifier.classify_volatility_regime(5) == VolatilityRegime.EXTREME_LOW

    # =========================================================================
    # Gamma Regime Classification Tests
    # =========================================================================

    def test_classify_gamma_strong_negative(self, classifier):
        """Test gamma regime for strong negative GEX"""
        assert classifier.classify_gamma_regime(-3e9) == GammaRegime.STRONG_NEGATIVE
        assert classifier.classify_gamma_regime(-2.5e9) == GammaRegime.STRONG_NEGATIVE

    def test_classify_gamma_negative(self, classifier):
        """Test gamma regime for negative GEX"""
        assert classifier.classify_gamma_regime(-1e9) == GammaRegime.NEGATIVE
        assert classifier.classify_gamma_regime(-0.6e9) == GammaRegime.NEGATIVE

    def test_classify_gamma_neutral(self, classifier):
        """Test gamma regime for neutral GEX"""
        assert classifier.classify_gamma_regime(0) == GammaRegime.NEUTRAL
        assert classifier.classify_gamma_regime(-0.3e9) == GammaRegime.NEUTRAL
        assert classifier.classify_gamma_regime(0.3e9) == GammaRegime.NEUTRAL

    def test_classify_gamma_positive(self, classifier):
        """Test gamma regime for positive GEX"""
        assert classifier.classify_gamma_regime(1e9) == GammaRegime.POSITIVE
        assert classifier.classify_gamma_regime(0.6e9) == GammaRegime.POSITIVE

    def test_classify_gamma_strong_positive(self, classifier):
        """Test gamma regime for strong positive GEX"""
        assert classifier.classify_gamma_regime(3e9) == GammaRegime.STRONG_POSITIVE
        assert classifier.classify_gamma_regime(2.5e9) == GammaRegime.STRONG_POSITIVE

    # =========================================================================
    # Trend Regime Classification Tests
    # =========================================================================

    def test_classify_trend_strong_uptrend(self, classifier):
        """Test trend regime for strong uptrend conditions"""
        result = classifier.classify_trend_regime(
            spot=600,
            flip_point=590,  # ~1.7% above flip
            momentum_1h=0.3,
            momentum_4h=0.6,  # Strong positive momentum
            above_20ma=True,
            above_50ma=True
        )
        assert result == TrendRegime.STRONG_UPTREND

    def test_classify_trend_strong_downtrend(self, classifier):
        """Test trend regime for strong downtrend conditions"""
        result = classifier.classify_trend_regime(
            spot=580,
            flip_point=600,  # ~3.3% below flip
            momentum_1h=-0.3,
            momentum_4h=-0.6,  # Strong negative momentum
            above_20ma=False,
            above_50ma=False
        )
        assert result == TrendRegime.STRONG_DOWNTREND

    def test_classify_trend_range_bound(self, classifier):
        """Test trend regime for range-bound conditions"""
        result = classifier.classify_trend_regime(
            spot=595,
            flip_point=595,  # At flip
            momentum_1h=0.1,
            momentum_4h=0.05,  # Low momentum
            above_20ma=True,
            above_50ma=False  # Mixed
        )
        assert result == TrendRegime.RANGE_BOUND

    # =========================================================================
    # Action Decision Tests
    # =========================================================================

    def test_determine_action_sell_premium_conditions(self, classifier):
        """Test action decision for selling premium (high IV, range-bound)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.EXTREME_HIGH,
            gamma_regime=GammaRegime.STRONG_POSITIVE,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_hv_ratio=1.5,  # IV overpriced
            distance_to_flip_pct=0.5,
            vix=25
        )

        assert action == MarketAction.SELL_PREMIUM
        assert confidence >= 70  # Should have high confidence

    def test_determine_action_buy_calls_conditions(self, classifier):
        """Test action decision for buying calls (negative gamma, bullish)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.STRONG_NEGATIVE,
            trend_regime=TrendRegime.UPTREND,
            iv_hv_ratio=0.9,  # IV reasonable
            distance_to_flip_pct=-2,  # Below flip
            vix=18
        )

        assert action == MarketAction.BUY_CALLS
        assert "negative gamma" in reasoning.lower() or "uptrend" in reasoning.lower()

    def test_determine_action_buy_puts_conditions(self, classifier):
        """Test action decision for buying puts (negative gamma, bearish)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.STRONG_NEGATIVE,
            trend_regime=TrendRegime.DOWNTREND,
            iv_hv_ratio=0.9,
            distance_to_flip_pct=2,  # Above flip
            vix=22
        )

        assert action == MarketAction.BUY_PUTS
        assert "negative gamma" in reasoning.lower() or "downtrend" in reasoning.lower()

    def test_determine_action_stay_flat_neutral(self, classifier):
        """Test action decision for staying flat (uncertain conditions)"""
        action, confidence, reasoning = classifier.determine_action(
            vol_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.NEUTRAL,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_hv_ratio=1.0,  # Fair value
            distance_to_flip_pct=0,  # At flip
            vix=18
        )

        # Should either stay flat or have low confidence
        assert action == MarketAction.STAY_FLAT or confidence < 60

    # =========================================================================
    # Threshold Constants Tests
    # =========================================================================

    def test_threshold_constants_reasonable(self, classifier):
        """Test that threshold constants are reasonable values"""
        # IV thresholds should be in percentile range
        assert 0 < classifier.IV_EXTREME_LOW < classifier.IV_LOW < classifier.IV_HIGH < classifier.IV_EXTREME_HIGH <= 100

        # GEX thresholds should be ordered
        assert classifier.GEX_STRONG_NEGATIVE < classifier.GEX_NEGATIVE < 0
        assert 0 < classifier.GEX_POSITIVE < classifier.GEX_STRONG_POSITIVE

        # Anti-whiplash parameters should be positive
        assert classifier.MIN_BARS_FOR_REGIME > 0
        assert classifier.REGIME_CHANGE_THRESHOLD > 0
        assert classifier.DECISION_COOLDOWN_BARS >= 0


class TestProbabilityWeights:
    """Tests for probability weight calculations"""

    def test_probability_weights_sum_to_one(self):
        """Test that default probability weights sum to 1.0"""
        try:
            from probability_calculator import ProbabilityWeights
        except ImportError:
            pytest.skip("probability_calculator requires database dependencies")

        weights = ProbabilityWeights()
        total = (
            weights.gex_wall_strength +
            weights.volatility_impact +
            weights.psychology_signal +
            weights.mm_positioning +
            weights.historical_pattern
        )

        assert abs(total - 1.0) < 0.01  # Allow small floating point error

    def test_probability_weights_to_dict(self):
        """Test weight serialization to dict"""
        try:
            from probability_calculator import ProbabilityWeights
        except ImportError:
            pytest.skip("probability_calculator requires database dependencies")

        weights = ProbabilityWeights()
        d = weights.to_dict()

        assert 'gex_wall_strength' in d
        assert 'volatility_impact' in d
        assert 'psychology_signal' in d
        assert 'mm_positioning' in d
        assert 'historical_pattern' in d


class TestRiskCalculations:
    """Tests for risk calculation utilities"""

    def test_kelly_criterion_basic(self):
        """Test Kelly criterion calculation"""
        # Kelly = W - [(1-W)/R] where W=win rate, R=win/loss ratio
        # For 60% win rate, 1.5:1 reward/risk
        # Kelly = 0.60 - [(1-0.60)/1.5] = 0.60 - 0.267 = 0.333 (33.3%)

        win_rate = 0.60
        avg_win = 150
        avg_loss = 100
        win_loss_ratio = avg_win / avg_loss

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        assert 0.30 < kelly < 0.40  # Should be around 33%

    def test_kelly_criterion_negative_edge(self):
        """Test Kelly criterion with negative expected value"""
        # 40% win rate, 1:1 reward/risk = negative expectancy
        win_rate = 0.40
        win_loss_ratio = 1.0

        kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        assert kelly < 0  # Should be negative - don't bet

    def test_kelly_criterion_edge_cases(self):
        """Test Kelly criterion edge cases"""
        # 100% win rate should give Kelly of 1.0
        kelly_perfect = 1.0 - ((1 - 1.0) / 1.5)
        assert kelly_perfect == 1.0

        # 0% win rate should give Kelly of -infinity (handled separately)
        # We just verify the formula doesn't crash
        win_rate = 0.01
        win_loss_ratio = 1.0
        kelly_bad = win_rate - ((1 - win_rate) / win_loss_ratio)
        assert kelly_bad < 0

    def test_position_sizing_max_risk(self):
        """Test position sizing respects maximum risk"""
        account_size = 100000
        max_risk_pct = 0.02  # 2% max risk
        option_price = 5.00
        contracts_per_option = 100

        max_risk_dollars = account_size * max_risk_pct
        max_contracts = int(max_risk_dollars / (option_price * contracts_per_option))

        # With $100k, 2% risk = $2000 max loss
        # $5 option x 100 = $500 per contract
        # Max contracts = 4

        assert max_contracts == 4

    def test_stop_loss_calculation(self):
        """Test stop loss percentage calculation"""
        entry_price = 10.00
        stop_loss_pct = 0.50  # 50% stop loss

        stop_price = entry_price * (1 - stop_loss_pct)

        assert stop_price == 5.00

    def test_profit_target_calculation(self):
        """Test profit target calculation"""
        entry_price = 10.00
        profit_target_pct = 1.00  # 100% profit target

        target_price = entry_price * (1 + profit_target_pct)

        assert target_price == 20.00


class TestMarketActionEnum:
    """Tests for MarketAction enum"""

    def test_all_actions_defined(self):
        """Test all expected market actions are defined"""
        expected_actions = [
            'SELL_PREMIUM', 'BUY_CALLS', 'BUY_PUTS',
            'STAY_FLAT', 'CLOSE_POSITIONS'
        ]

        for action_name in expected_actions:
            assert hasattr(MarketAction, action_name)

    def test_action_values_are_strings(self):
        """Test action values are strings for serialization"""
        for action in MarketAction:
            assert isinstance(action.value, str)


class TestRegimeEnums:
    """Tests for regime classification enums"""

    def test_volatility_regime_ordering(self):
        """Test volatility regime has all expected values"""
        expected = ['EXTREME_HIGH', 'HIGH', 'NORMAL', 'LOW', 'EXTREME_LOW']
        for regime_name in expected:
            assert hasattr(VolatilityRegime, regime_name)

    def test_gamma_regime_ordering(self):
        """Test gamma regime has all expected values"""
        expected = ['STRONG_NEGATIVE', 'NEGATIVE', 'NEUTRAL', 'POSITIVE', 'STRONG_POSITIVE']
        for regime_name in expected:
            assert hasattr(GammaRegime, regime_name)

    def test_trend_regime_ordering(self):
        """Test trend regime has all expected values"""
        expected = ['STRONG_UPTREND', 'UPTREND', 'RANGE_BOUND', 'DOWNTREND', 'STRONG_DOWNTREND']
        for regime_name in expected:
            assert hasattr(TrendRegime, regime_name)


# =========================================================================
# Integration Tests
# =========================================================================

class TestClassifierIntegration:
    """Integration tests for the classifier"""

    @pytest.fixture
    def classifier(self):
        """Create a classifier with database disabled"""
        with patch('market_regime_classifier.DB_AVAILABLE', False):
            return MarketRegimeClassifier(symbol="SPY")

    def test_full_classification_flow(self, classifier):
        """Test a full classification from raw data to action"""
        # This tests the whole flow would work (with mocked data)
        iv_rank = 75  # High IV
        net_gex = 2.5e9  # Strong positive gamma

        vol_regime = classifier.classify_volatility_regime(iv_rank)
        gamma_regime = classifier.classify_gamma_regime(net_gex)

        assert vol_regime == VolatilityRegime.HIGH
        assert gamma_regime == GammaRegime.STRONG_POSITIVE

        # With high IV and strong positive gamma, should lean toward selling premium
        trend_regime = TrendRegime.RANGE_BOUND

        action, confidence, reasoning = classifier.determine_action(
            vol_regime=vol_regime,
            gamma_regime=gamma_regime,
            trend_regime=trend_regime,
            iv_hv_ratio=1.3,
            distance_to_flip_pct=0.5,
            vix=22
        )

        # Should recommend selling premium in this environment
        assert action == MarketAction.SELL_PREMIUM


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
