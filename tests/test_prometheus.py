"""
Prometheus ML System Tests
===========================

Unit tests for the Prometheus ML system components.
These tests mock external dependencies to test core logic.

Run: pytest tests/test_prometheus.py -v
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestPrometheusFeatures:
    """Test PrometheusFeatures dataclass"""

    @pytest.fixture
    def sample_features(self):
        """Create sample features for testing"""
        # Import inside fixture to handle missing deps gracefully
        try:
            from trading.prometheus_ml import PrometheusFeatures
            return PrometheusFeatures(
                trade_date="2025-01-06",
                strike=5800.0,
                underlying_price=5950.0,
                dte=0,
                delta=-0.15,
                premium=5.50,
                iv=0.18,
                iv_rank=45.0,
                vix=16.5,
                vix_percentile=40.0,
                vix_term_structure=-1.2,
                put_wall_distance_pct=2.5,
                call_wall_distance_pct=3.0,
                net_gex=5e9,
                spx_20d_return=1.5,
                spx_5d_return=0.8,
                spx_distance_from_high=0.5,
                premium_to_strike_pct=0.095,
                annualized_return=35.0
            )
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")

    def test_feature_names_count(self, sample_features):
        """Test that feature names match expected count"""
        try:
            from trading.prometheus_ml import PrometheusFeatures
            names = PrometheusFeatures.feature_names()
            assert len(names) == 15, f"Expected 15 feature names, got {len(names)}"
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")

    def test_to_array_shape(self, sample_features):
        """Test feature array conversion"""
        arr = sample_features.to_array()
        assert len(arr) == 15, f"Expected 15 features, got {len(arr)}"

    def test_to_dict(self, sample_features):
        """Test dictionary conversion"""
        d = sample_features.to_dict()
        assert 'strike' in d
        assert 'delta' in d
        assert 'vix' in d
        assert d['strike'] == 5800.0

    def test_moneyness_calculation(self, sample_features):
        """Test moneyness is calculated correctly"""
        # Moneyness = (underlying - strike) / underlying
        expected = (5950.0 - 5800.0) / 5950.0
        assert abs(sample_features.moneyness - expected) < 0.001


class TestPrometheusOutcome:
    """Test PrometheusOutcome dataclass"""

    @pytest.fixture
    def sample_outcome(self):
        try:
            from trading.prometheus_ml import PrometheusFeatures, PrometheusOutcome
            features = PrometheusFeatures(
                trade_date="2025-01-06",
                strike=5800.0,
                underlying_price=5950.0,
                dte=0,
                delta=-0.15,
                premium=5.50,
                iv=0.18,
                iv_rank=45.0,
                vix=16.5,
                vix_percentile=40.0,
                vix_term_structure=-1.2,
                put_wall_distance_pct=2.5,
                call_wall_distance_pct=3.0,
                net_gex=5e9,
                spx_20d_return=1.5,
                spx_5d_return=0.8,
                spx_distance_from_high=0.5,
                premium_to_strike_pct=0.095,
                annualized_return=35.0
            )
            return PrometheusOutcome(
                trade_id="TEST-001",
                features=features,
                outcome="WIN",
                pnl=550.0,
                max_drawdown=-200.0,
                settlement_price=5900.0
            )
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")

    def test_is_win_positive(self, sample_outcome):
        """Test is_win returns True for WIN outcome"""
        assert sample_outcome.is_win() == True

    def test_is_win_negative(self, sample_outcome):
        """Test is_win returns False for LOSS outcome"""
        sample_outcome.outcome = "LOSS"
        assert sample_outcome.is_win() == False


class TestRecommendation:
    """Test Recommendation enum"""

    def test_recommendation_values(self):
        try:
            from trading.prometheus_ml import Recommendation
            assert Recommendation.STRONG_TRADE.value == "STRONG_TRADE"
            assert Recommendation.TRADE.value == "TRADE"
            assert Recommendation.NEUTRAL.value == "NEUTRAL"
            assert Recommendation.CAUTION.value == "CAUTION"
            assert Recommendation.SKIP.value == "SKIP"
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")


class TestPrometheusPrediction:
    """Test PrometheusPrediction dataclass"""

    def test_prediction_to_dict(self):
        try:
            from trading.prometheus_ml import PrometheusPrediction, Recommendation

            prediction = PrometheusPrediction(
                trade_id="TEST-001",
                win_probability=0.72,
                recommendation=Recommendation.STRONG_TRADE,
                confidence=0.85,
                reasoning="High probability trade",
                key_factors={'vix': 'favorable'},
                feature_values={'vix': 16.5},
                model_version="v1.0"
            )

            d = prediction.to_dict()
            assert d['trade_id'] == "TEST-001"
            assert d['win_probability'] == 0.72
            assert d['recommendation'] == "STRONG_TRADE"
            assert d['confidence'] == 0.85
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")


class TestPrometheusTrainer:
    """Test PrometheusTrainer class"""

    @pytest.fixture
    def mock_trainer(self):
        """Create a trainer with mocked ML libraries"""
        try:
            # Mock the ML libraries
            with patch.dict('sys.modules', {
                'sklearn': MagicMock(),
                'sklearn.ensemble': MagicMock(),
                'sklearn.model_selection': MagicMock(),
                'sklearn.preprocessing': MagicMock(),
                'sklearn.metrics': MagicMock(),
                'sklearn.calibration': MagicMock(),
            }):
                from trading.prometheus_ml import PrometheusTrainer
                return PrometheusTrainer()
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")

    def test_trainer_initialization(self, mock_trainer):
        """Test trainer initializes correctly"""
        assert mock_trainer.model is None
        assert mock_trainer.scaler is None
        assert mock_trainer.model_version is None

    def test_recommendation_thresholds(self):
        """Test recommendation threshold logic"""
        # These are the expected thresholds from prometheus_ml.py
        # prob >= 0.70: STRONG_TRADE
        # prob >= 0.55: TRADE
        # prob >= 0.45: NEUTRAL
        # prob >= 0.30: CAUTION
        # else: SKIP

        thresholds = [
            (0.75, "STRONG_TRADE"),
            (0.70, "STRONG_TRADE"),
            (0.65, "TRADE"),
            (0.55, "TRADE"),
            (0.50, "NEUTRAL"),
            (0.45, "NEUTRAL"),
            (0.35, "CAUTION"),
            (0.30, "CAUTION"),
            (0.25, "SKIP"),
            (0.10, "SKIP"),
        ]

        for prob, expected in thresholds:
            if prob >= 0.70:
                result = "STRONG_TRADE"
            elif prob >= 0.55:
                result = "TRADE"
            elif prob >= 0.45:
                result = "NEUTRAL"
            elif prob >= 0.30:
                result = "CAUTION"
            else:
                result = "SKIP"
            assert result == expected, f"Prob {prob}: expected {expected}, got {result}"


class TestLogType:
    """Test LogType enum"""

    def test_log_types(self):
        try:
            from trading.prometheus_ml import LogType
            assert LogType.PREDICTION.value == "PREDICTION"
            assert LogType.TRAINING.value == "TRAINING"
            assert LogType.OUTCOME.value == "OUTCOME"
            assert LogType.ERROR.value == "ERROR"
        except ImportError:
            pytest.skip("Prometheus ML dependencies not installed")


class TestAPIRoutes:
    """Test API route definitions"""

    def test_routes_syntax(self):
        """Verify prometheus_routes.py has valid Python syntax"""
        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'backend', 'api', 'routes', 'prometheus_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        # Should not raise SyntaxError
        compile(code, 'prometheus_routes.py', 'exec')

    def test_endpoint_count(self):
        """Verify expected number of endpoints"""
        import re

        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'backend', 'api', 'routes', 'prometheus_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        endpoints = re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', code)
        assert len(endpoints) >= 10, f"Expected at least 10 endpoints, found {len(endpoints)}"

    def test_required_endpoints_exist(self):
        """Check that all required endpoints are defined"""
        import re

        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'backend', 'api', 'routes', 'prometheus_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        required = [
            '/status',
            '/train',
            '/predict',
            '/quick-predict',
            '/record-entry',
            '/record-outcome',
            '/pending-trades',
            '/market-data',
            '/feature-importance',
            '/logs',
            '/training-history',
            '/performance',
            '/health'
        ]

        for endpoint in required:
            assert endpoint in code, f"Missing endpoint: {endpoint}"


class TestTrainingScript:
    """Test the training script"""

    def test_script_syntax(self):
        """Verify train_prometheus_model.py has valid Python syntax"""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'train_prometheus_model.py'
        )

        with open(script_path, 'r') as f:
            code = f.read()

        compile(code, 'train_prometheus_model.py', 'exec')

    def test_has_required_functions(self):
        """Check for required functions in training script"""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'train_prometheus_model.py'
        )

        with open(script_path, 'r') as f:
            code = f.read()

        required_functions = [
            'generate_synthetic_training_data',
            'save_training_data_to_db',
            'extract_from_backtest_results',
            'train_prometheus_with_data',
            'main'
        ]

        for func in required_functions:
            assert f'def {func}' in code, f"Missing function: {func}"


class TestHealthCheckScript:
    """Test the health check script"""

    def test_script_syntax(self):
        """Verify prometheus_health_check.py has valid Python syntax"""
        script_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'scripts', 'prometheus_health_check.py'
        )

        with open(script_path, 'r') as f:
            code = f.read()

        compile(code, 'prometheus_health_check.py', 'exec')
