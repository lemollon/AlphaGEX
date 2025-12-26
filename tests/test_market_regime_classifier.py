"""
Comprehensive Tests for Market Regime Classifier

Tests the unified market regime classification system including:
- Regime enumeration types
- IV rank calculations
- Regime classification logic
- Anti-whiplash mechanisms
- State persistence

Run with: pytest tests/test_market_regime_classifier.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestMarketActionEnum:
    """Tests for MarketAction enumeration"""

    def test_all_actions_defined(self):
        """Test all market actions are defined"""
        from core.market_regime_classifier import MarketAction

        assert hasattr(MarketAction, 'SELL_PREMIUM')
        assert hasattr(MarketAction, 'BUY_CALLS')
        assert hasattr(MarketAction, 'BUY_PUTS')
        assert hasattr(MarketAction, 'STAY_FLAT')
        assert hasattr(MarketAction, 'CLOSE_POSITIONS')

    def test_action_values(self):
        """Test action values are strings"""
        from core.market_regime_classifier import MarketAction

        assert MarketAction.SELL_PREMIUM.value == "SELL_PREMIUM"
        assert MarketAction.STAY_FLAT.value == "STAY_FLAT"


class TestVolatilityRegimeEnum:
    """Tests for VolatilityRegime enumeration"""

    def test_all_regimes_defined(self):
        """Test all volatility regimes are defined"""
        from core.market_regime_classifier import VolatilityRegime

        assert hasattr(VolatilityRegime, 'EXTREME_HIGH')
        assert hasattr(VolatilityRegime, 'HIGH')
        assert hasattr(VolatilityRegime, 'NORMAL')
        assert hasattr(VolatilityRegime, 'LOW')
        assert hasattr(VolatilityRegime, 'EXTREME_LOW')


class TestGammaRegimeEnum:
    """Tests for GammaRegime enumeration"""

    def test_all_regimes_defined(self):
        """Test all gamma regimes are defined"""
        from core.market_regime_classifier import GammaRegime

        assert hasattr(GammaRegime, 'STRONG_NEGATIVE')
        assert hasattr(GammaRegime, 'NEGATIVE')
        assert hasattr(GammaRegime, 'NEUTRAL')
        assert hasattr(GammaRegime, 'POSITIVE')
        assert hasattr(GammaRegime, 'STRONG_POSITIVE')


class TestTrendRegimeEnum:
    """Tests for TrendRegime enumeration"""

    def test_all_regimes_defined(self):
        """Test all trend regimes are defined"""
        from core.market_regime_classifier import TrendRegime

        assert hasattr(TrendRegime, 'STRONG_UPTREND')
        assert hasattr(TrendRegime, 'UPTREND')
        assert hasattr(TrendRegime, 'RANGE_BOUND')
        assert hasattr(TrendRegime, 'DOWNTREND')
        assert hasattr(TrendRegime, 'STRONG_DOWNTREND')


class TestRegimeClassificationDataclass:
    """Tests for RegimeClassification dataclass"""

    def test_can_create_classification(self):
        """Test RegimeClassification can be instantiated"""
        from core.market_regime_classifier import (
            RegimeClassification,
            VolatilityRegime,
            GammaRegime,
            TrendRegime,
            MarketAction
        )

        classification = RegimeClassification(
            timestamp=datetime.now(CENTRAL_TZ),
            symbol='SPY',
            volatility_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.POSITIVE,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_rank=45.0,
            iv_percentile=50.0,
            current_iv=0.18,
            historical_vol=0.15,
            iv_hv_ratio=1.2,
            net_gex=1.5e9,
            flip_point=583.0,
            spot_price=585.0,
            distance_to_flip_pct=0.34,
            vix=15.0,
            vix_term_structure='contango',
            recommended_action=MarketAction.SELL_PREMIUM,
            confidence=75.0,
            reasoning='Normal conditions favor premium selling',
            regime_start_time=datetime.now(CENTRAL_TZ),
            bars_in_regime=5,
            regime_changed=False,
            max_position_size_pct=0.02,
            stop_loss_pct=0.50,
            profit_target_pct=0.50
        )

        assert classification.symbol == 'SPY'
        assert classification.recommended_action == MarketAction.SELL_PREMIUM


class TestMarketRegimeClassifier:
    """Tests for MarketRegimeClassifier class"""

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_classifier_initialization(self):
        """Test classifier initializes correctly"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier(symbol='SPY')

        assert classifier.symbol == 'SPY'
        assert classifier.current_regime is None
        assert classifier.bars_in_current_regime == 0

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_classifier_with_custom_symbol(self):
        """Test classifier with custom symbol"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier(symbol='QQQ')

        assert classifier.symbol == 'QQQ'


class TestIVRankCalculation:
    """Tests for IV rank calculation"""

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_iv_rank_calculation_basic(self):
        """Test basic IV rank calculation"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # IV at 0.20, history from 0.15 to 0.25
        iv_history = [0.15 + 0.01 * i for i in range(11)]  # 0.15 to 0.25
        current_iv = 0.20

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        # IV rank should be 50% (midpoint of range)
        assert 40 <= iv_rank <= 60

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_iv_rank_at_high(self):
        """Test IV rank when at 52-week high"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        iv_history = [0.15 + 0.01 * i for i in range(11)]
        current_iv = 0.25  # At the high

        iv_rank, _ = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank >= 90

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_iv_rank_at_low(self):
        """Test IV rank when at 52-week low"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        iv_history = [0.15 + 0.01 * i for i in range(11)]
        current_iv = 0.15  # At the low

        iv_rank, _ = classifier.calculate_iv_rank(current_iv, iv_history)

        assert iv_rank <= 10

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_iv_rank_insufficient_history(self):
        """Test IV rank with insufficient history"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        iv_history = [0.18, 0.19]  # Only 2 values
        current_iv = 0.185

        iv_rank, iv_percentile = classifier.calculate_iv_rank(current_iv, iv_history)

        # Should return defaults
        assert 0 <= iv_rank <= 100
        assert 0 <= iv_percentile <= 100


class TestAntiWhiplashMechanisms:
    """Tests for anti-whiplash mechanisms"""

    def test_min_bars_for_regime_defined(self):
        """Test MIN_BARS_FOR_REGIME is defined"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert hasattr(MarketRegimeClassifier, 'MIN_BARS_FOR_REGIME')
        assert MarketRegimeClassifier.MIN_BARS_FOR_REGIME >= 1

    def test_regime_change_threshold_defined(self):
        """Test REGIME_CHANGE_THRESHOLD is defined"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert hasattr(MarketRegimeClassifier, 'REGIME_CHANGE_THRESHOLD')
        assert 0 < MarketRegimeClassifier.REGIME_CHANGE_THRESHOLD < 1

    def test_decision_cooldown_bars_defined(self):
        """Test DECISION_COOLDOWN_BARS is defined"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert hasattr(MarketRegimeClassifier, 'DECISION_COOLDOWN_BARS')
        assert MarketRegimeClassifier.DECISION_COOLDOWN_BARS >= 1


class TestGEXThresholds:
    """Tests for GEX classification thresholds"""

    def test_gex_thresholds_ordered(self):
        """Test GEX thresholds are properly ordered"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert MarketRegimeClassifier.GEX_STRONG_NEGATIVE < MarketRegimeClassifier.GEX_NEGATIVE
        assert MarketRegimeClassifier.GEX_NEGATIVE < MarketRegimeClassifier.GEX_POSITIVE
        assert MarketRegimeClassifier.GEX_POSITIVE < MarketRegimeClassifier.GEX_STRONG_POSITIVE

    def test_gex_thresholds_symmetric(self):
        """Test GEX thresholds are roughly symmetric"""
        from core.market_regime_classifier import MarketRegimeClassifier

        # Strong positive/negative should have same magnitude
        assert abs(MarketRegimeClassifier.GEX_STRONG_NEGATIVE) == MarketRegimeClassifier.GEX_STRONG_POSITIVE


class TestIVThresholds:
    """Tests for IV rank classification thresholds"""

    def test_iv_thresholds_ordered(self):
        """Test IV thresholds are properly ordered"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert MarketRegimeClassifier.IV_EXTREME_LOW < MarketRegimeClassifier.IV_LOW
        assert MarketRegimeClassifier.IV_LOW < MarketRegimeClassifier.IV_HIGH
        assert MarketRegimeClassifier.IV_HIGH < MarketRegimeClassifier.IV_EXTREME_HIGH

    def test_iv_thresholds_valid_range(self):
        """Test IV thresholds are in valid range (0-100)"""
        from core.market_regime_classifier import MarketRegimeClassifier

        assert 0 <= MarketRegimeClassifier.IV_EXTREME_LOW <= 100
        assert 0 <= MarketRegimeClassifier.IV_EXTREME_HIGH <= 100


class TestStatePersistence:
    """Tests for regime state persistence"""

    @patch('core.market_regime_classifier.DB_AVAILABLE', True)
    @patch('core.market_regime_classifier.get_connection')
    def test_load_persisted_state(self, mock_conn):
        """Test loading persisted state from database"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            '{"bars_in_regime": 10, "recommended_action": "SELL_PREMIUM"}',
            datetime.now() - timedelta(minutes=30)
        )
        mock_conn.return_value.cursor.return_value = mock_cursor

        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # Should have loaded state
        assert classifier.bars_in_current_regime == 10

    @patch('core.market_regime_classifier.DB_AVAILABLE', True)
    @patch('core.market_regime_classifier.get_connection')
    def test_ignore_old_persisted_state(self, mock_conn):
        """Test ignoring state older than 1 hour"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            '{"bars_in_regime": 10}',
            datetime.now() - timedelta(hours=2)  # Old state
        )
        mock_conn.return_value.cursor.return_value = mock_cursor

        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # Should NOT have loaded old state
        assert classifier.bars_in_current_regime == 0


class TestVolatilitySurfaceIntegration:
    """Tests for volatility surface integration"""

    def test_vol_surface_fields_optional(self):
        """Test vol surface fields are optional in classification"""
        from core.market_regime_classifier import (
            RegimeClassification,
            VolatilityRegime,
            GammaRegime,
            TrendRegime,
            MarketAction
        )

        classification = RegimeClassification(
            timestamp=datetime.now(CENTRAL_TZ),
            symbol='SPY',
            volatility_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.POSITIVE,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_rank=45.0,
            iv_percentile=50.0,
            current_iv=0.18,
            historical_vol=0.15,
            iv_hv_ratio=1.2,
            net_gex=1.5e9,
            flip_point=583.0,
            spot_price=585.0,
            distance_to_flip_pct=0.34,
            vix=15.0,
            vix_term_structure='contango',
            recommended_action=MarketAction.SELL_PREMIUM,
            confidence=75.0,
            reasoning='Test',
            regime_start_time=datetime.now(CENTRAL_TZ),
            bars_in_regime=1,
            regime_changed=False,
            max_position_size_pct=0.02,
            stop_loss_pct=0.50,
            profit_target_pct=0.50
        )

        # Optional fields should default to None
        assert classification.skew_regime is None
        assert classification.term_structure_regime is None


class TestMLIntegration:
    """Tests for ML pattern learner integration"""

    def test_ml_fields_optional(self):
        """Test ML fields are optional in classification"""
        from core.market_regime_classifier import (
            RegimeClassification,
            VolatilityRegime,
            GammaRegime,
            TrendRegime,
            MarketAction
        )

        classification = RegimeClassification(
            timestamp=datetime.now(CENTRAL_TZ),
            symbol='SPY',
            volatility_regime=VolatilityRegime.NORMAL,
            gamma_regime=GammaRegime.POSITIVE,
            trend_regime=TrendRegime.RANGE_BOUND,
            iv_rank=45.0,
            iv_percentile=50.0,
            current_iv=0.18,
            historical_vol=0.15,
            iv_hv_ratio=1.2,
            net_gex=1.5e9,
            flip_point=583.0,
            spot_price=585.0,
            distance_to_flip_pct=0.34,
            vix=15.0,
            vix_term_structure='contango',
            recommended_action=MarketAction.SELL_PREMIUM,
            confidence=75.0,
            reasoning='Test',
            regime_start_time=datetime.now(CENTRAL_TZ),
            bars_in_regime=1,
            regime_changed=False,
            max_position_size_pct=0.02,
            stop_loss_pct=0.50,
            profit_target_pct=0.50
        )

        # ML fields should default to None/False
        assert classification.ml_win_probability is None
        assert classification.ml_model_trained is False


class TestEdgeCases:
    """Tests for edge cases"""

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_handles_zero_gex(self):
        """Test handling of zero GEX"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # Should not raise with zero GEX
        # The classifier should handle this gracefully

    @patch('core.market_regime_classifier.DB_AVAILABLE', False)
    def test_handles_extreme_values(self):
        """Test handling of extreme values"""
        from core.market_regime_classifier import MarketRegimeClassifier

        classifier = MarketRegimeClassifier()

        # Test with extreme IV
        iv_history = [0.5] * 50
        iv_rank, iv_percentile = classifier.calculate_iv_rank(0.8, iv_history)

        assert 0 <= iv_rank <= 100
        assert 0 <= iv_percentile <= 100
