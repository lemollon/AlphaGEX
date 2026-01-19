"""
ORION - GEX Probability Models Tests

Tests for the 5 XGBoost models used by ARGUS and HYPERION for strike probability.

Models:
1. Direction Probability - UP/DOWN/FLAT classification
2. Flip Gravity - Probability price moves toward flip point
3. Magnet Attraction - Probability price reaches nearest magnet
4. Volatility Estimate - Expected price range prediction
5. Pin Zone Behavior - Probability of staying pinned

Run with: pytest tests/test_gex_probability_models.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# Import Tests
# ============================================================================

class TestOrionImports:
    """Test that all ORION components can be imported"""

    def test_import_gex_probability_models(self):
        """Test GEXProbabilityModels wrapper can be imported"""
        try:
            from quant.gex_probability_models import GEXProbabilityModels
            assert GEXProbabilityModels is not None
        except ImportError as e:
            pytest.skip(f"GEXProbabilityModels not available: {e}")

    def test_import_gex_signal_generator(self):
        """Test GEXSignalGenerator can be imported"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator
            assert GEXSignalGenerator is not None
        except ImportError as e:
            pytest.skip(f"GEXSignalGenerator not available: {e}")

    def test_import_direction_enum(self):
        """Test Direction enum can be imported"""
        try:
            from quant.gex_probability_models import Direction
            assert Direction.UP.value == "UP"
            assert Direction.DOWN.value == "DOWN"
            assert Direction.FLAT.value == "FLAT"
        except ImportError as e:
            pytest.skip(f"Direction enum not available: {e}")

    def test_import_combined_signal(self):
        """Test CombinedSignal dataclass can be imported"""
        try:
            from quant.gex_probability_models import CombinedSignal
            assert CombinedSignal is not None
        except ImportError as e:
            pytest.skip(f"CombinedSignal not available: {e}")


# ============================================================================
# GEXProbabilityModels Wrapper Tests
# ============================================================================

class TestGEXProbabilityModelsWrapper:
    """Tests for the GEXProbabilityModels singleton wrapper"""

    def test_singleton_pattern(self):
        """Test that GEXProbabilityModels uses singleton pattern"""
        try:
            from quant.gex_probability_models import GEXProbabilityModels

            instance1 = GEXProbabilityModels()
            instance2 = GEXProbabilityModels()

            assert instance1 is instance2, "Should return same instance"
        except ImportError:
            pytest.skip("GEXProbabilityModels not available")

    def test_is_trained_property(self):
        """Test is_trained property exists"""
        try:
            from quant.gex_probability_models import GEXProbabilityModels

            models = GEXProbabilityModels()
            assert hasattr(models, 'is_trained')
            assert isinstance(models.is_trained, bool)
        except ImportError:
            pytest.skip("GEXProbabilityModels not available")

    def test_model_info_property(self):
        """Test model_info property exists"""
        try:
            from quant.gex_probability_models import GEXProbabilityModels

            models = GEXProbabilityModels()
            assert hasattr(models, 'model_info')
            # model_info can be None if not trained
            info = models.model_info
            assert info is None or isinstance(info, dict)
        except ImportError:
            pytest.skip("GEXProbabilityModels not available")


# ============================================================================
# GEXSignalGenerator Tests
# ============================================================================

class TestGEXSignalGenerator:
    """Tests for the GEXSignalGenerator training and prediction"""

    def test_generator_initialization(self):
        """Test generator can be initialized"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator

            generator = GEXSignalGenerator()
            assert generator is not None
            assert hasattr(generator, 'is_trained')
        except ImportError:
            pytest.skip("GEXSignalGenerator not available")

    def test_generator_has_sub_models(self):
        """Test generator has all 5 sub-model attributes"""
        try:
            from quant.gex_probability_models import GEXSignalGenerator

            generator = GEXSignalGenerator()

            # Check all 5 sub-models exist
            assert hasattr(generator, 'direction_model')
            assert hasattr(generator, 'flip_gravity_model')
            assert hasattr(generator, 'magnet_attraction_model')
            assert hasattr(generator, 'volatility_model')
            assert hasattr(generator, 'pin_zone_model')
        except ImportError:
            pytest.skip("GEXSignalGenerator not available")


# ============================================================================
# Feature Engineering Tests
# ============================================================================

class TestFeatureEngineering:
    """Tests for feature engineering functions"""

    def test_engineer_features_function_exists(self):
        """Test engineer_features function exists"""
        try:
            from quant.gex_probability_models import engineer_features
            assert callable(engineer_features)
        except ImportError:
            pytest.skip("engineer_features not available")

    def test_engineer_features_with_mock_data(self):
        """Test feature engineering with mock data"""
        try:
            import pandas as pd
            from quant.gex_probability_models import engineer_features

            # Create minimal mock dataframe
            df = pd.DataFrame({
                'trade_date': ['2024-01-01', '2024-01-02'],
                'symbol': ['SPY', 'SPY'],
                'spot_open': [580.0, 582.0],
                'spot_close': [582.0, 581.0],
                'spot_high': [583.0, 584.0],
                'spot_low': [579.0, 580.0],
                'net_gamma': [1000000, -500000],
                'total_call_gamma': [2000000, 1500000],
                'total_put_gamma': [1000000, 2000000],
                'flip_point': [580.0, 581.0],
                'magnet_1_strike': [585.0, 585.0],
                'magnet_1_gamma': [500000, 400000],
                'magnet_2_strike': [575.0, 575.0],
                'magnet_2_gamma': [300000, 350000],
                'magnet_3_strike': [590.0, 590.0],
                'magnet_3_gamma': [200000, 250000],
                'call_wall': [590.0, 590.0],
                'put_wall': [570.0, 570.0],
                'gamma_above_spot': [800000, 600000],
                'gamma_below_spot': [200000, 400000],
                'gamma_imbalance_pct': [60.0, -40.0],
                'num_magnets_above': [2, 2],
                'num_magnets_below': [1, 1],
                'nearest_magnet_strike': [585.0, 585.0],
                'nearest_magnet_distance_pct': [0.86, 0.51],
                'open_to_flip_distance_pct': [0.0, 0.17],
                'open_in_pin_zone': [True, False],
                'price_change_pct': [0.34, -0.17],
                'price_range_pct': [0.69, 0.69],
                'close_distance_to_flip_pct': [0.34, 0.0],
                'close_distance_to_magnet1_pct': [0.51, 0.69],
                'close_distance_to_magnet2_pct': [1.21, 1.03],
                'vix_open': [15.0, 16.0],
                'vix_close': [15.5, 15.8]
            })

            result = engineer_features(df)

            # Check new features were added
            assert 'gamma_regime' in result.columns
            assert 'gamma_regime_positive' in result.columns
            assert 'net_gamma_normalized' in result.columns
            assert 'gamma_ratio' in result.columns
            assert 'vix_level' in result.columns

        except ImportError:
            pytest.skip("Feature engineering not available")


# ============================================================================
# Data Loading Tests
# ============================================================================

class TestDataLoading:
    """Tests for data loading functions"""

    def test_load_gex_structure_data_exists(self):
        """Test load_gex_structure_data function exists"""
        try:
            from quant.gex_probability_models import load_gex_structure_data
            assert callable(load_gex_structure_data)
        except ImportError:
            pytest.skip("load_gex_structure_data not available")

    def test_load_gex_from_history_fallback_exists(self):
        """Test fallback loader function exists"""
        try:
            from quant.gex_probability_models import load_gex_from_history_fallback
            assert callable(load_gex_from_history_fallback)
        except ImportError:
            pytest.skip("load_gex_from_history_fallback not available")


# ============================================================================
# Prediction Tests (Mocked)
# ============================================================================

class TestPredictions:
    """Tests for prediction methods with mocked models"""

    def test_predict_magnet_attraction_untrained(self):
        """Test magnet attraction prediction returns None when untrained"""
        try:
            from quant.gex_probability_models import GEXProbabilityModels

            models = GEXProbabilityModels()

            gamma_structure = {
                'net_gamma': 1000000,
                'flip_point': 580.0,
                'magnets': [{'strike': 585.0, 'gamma': 500000}],
                'vix': 15.0,
                'gamma_regime': 'POSITIVE',
                'expected_move': 2.5,
                'spot_price': 582.0
            }

            result = models.predict_magnet_attraction(
                strike=585.0,
                spot_price=582.0,
                gamma_structure=gamma_structure
            )

            # If not trained, should return None
            if not models.is_trained:
                assert result is None

        except ImportError:
            pytest.skip("GEXProbabilityModels not available")


# ============================================================================
# Integration with ARGUS/HYPERION
# ============================================================================

class TestIntegration:
    """Tests for ARGUS/HYPERION integration"""

    def test_argus_engine_import(self):
        """Test ARGUS engine can import GEXProbabilityModels"""
        try:
            from core.argus_engine import ARGUSEngine

            engine = ARGUSEngine()

            # Check ML methods exist
            assert hasattr(engine, '_get_ml_models')
            assert hasattr(engine, 'get_ml_status')
            assert hasattr(engine, 'calculate_probability_hybrid')

        except ImportError:
            pytest.skip("ARGUSEngine not available")

    def test_shared_engine_import(self):
        """Test shared gamma engine has ML integration"""
        try:
            from core.shared_gamma_engine import SharedGammaEngine

            engine = SharedGammaEngine()

            # Check ML methods exist
            assert hasattr(engine, 'get_ml_status')
            assert hasattr(engine, 'calculate_probability_hybrid')

        except ImportError:
            pytest.skip("SharedGammaEngine not available")


# ============================================================================
# Combined Signal Tests
# ============================================================================

class TestCombinedSignal:
    """Tests for CombinedSignal dataclass"""

    def test_combined_signal_creation(self):
        """Test CombinedSignal can be created"""
        try:
            from quant.gex_probability_models import CombinedSignal

            signal = CombinedSignal(
                direction_prediction='UP',
                direction_confidence=0.75,
                flip_gravity_prob=0.60,
                magnet_attraction_prob=0.55,
                expected_volatility_pct=1.5,
                pin_zone_prob=0.40,
                overall_conviction=0.65,
                trade_recommendation='LONG'
            )

            assert signal.direction_prediction == 'UP'
            assert signal.direction_confidence == 0.75
            assert signal.overall_conviction == 0.65

        except ImportError:
            pytest.skip("CombinedSignal not available")

    def test_combined_signal_to_dict(self):
        """Test CombinedSignal.to_dict() method"""
        try:
            from quant.gex_probability_models import CombinedSignal

            signal = CombinedSignal(
                direction_prediction='DOWN',
                direction_confidence=0.80,
                flip_gravity_prob=0.70,
                magnet_attraction_prob=0.45,
                expected_volatility_pct=2.0,
                pin_zone_prob=0.30,
                overall_conviction=0.55,
                trade_recommendation='SHORT'
            )

            result = signal.to_dict()

            assert isinstance(result, dict)
            assert result['direction'] == 'DOWN'
            assert result['conviction'] == 0.55
            assert result['recommendation'] == 'SHORT'

        except ImportError:
            pytest.skip("CombinedSignal not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
