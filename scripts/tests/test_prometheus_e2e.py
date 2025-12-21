#!/usr/bin/env python3
"""
PROMETHEUS End-to-End Tests
============================

Comprehensive tests for the Prometheus ML system including:
- API endpoint testing
- ML training workflow
- Prediction accuracy
- Logging and tracing
- Database persistence
- Performance metrics

Author: AlphaGEX Quant
"""

import os
import sys
import json
import time
import uuid
import unittest
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Try imports
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("Warning: requests not installed. API tests will be skipped.")

try:
    from trading.prometheus_ml import (
        PrometheusMLTrainer,
        PrometheusFeatures,
        PrometheusOutcome,
        PrometheusLogger,
        LogType,
        Recommendation,
        get_prometheus_trainer,
        get_prometheus_logger,
        ML_AVAILABLE,
        DB_AVAILABLE
    )
    PROMETHEUS_AVAILABLE = True
except ImportError as e:
    PROMETHEUS_AVAILABLE = False
    ML_AVAILABLE = False
    DB_AVAILABLE = False
    print(f"Warning: Prometheus ML not available: {e}")


class TestPrometheusML(unittest.TestCase):
    """Test Prometheus ML core functionality"""

    def setUp(self):
        """Set up test fixtures"""
        if not PROMETHEUS_AVAILABLE:
            self.skipTest("Prometheus ML not available")

        self.trainer = PrometheusMLTrainer()
        self.logger = get_prometheus_logger()

    def test_feature_creation(self):
        """Test PrometheusFeatures dataclass"""
        features = PrometheusFeatures(
            trade_date="2024-01-15",
            strike=5800.0,
            underlying_price=5850.0,
            dte=1,
            delta=-0.15,
            premium=5.50,
            iv=0.18,
            iv_rank=55.0,
            vix=18.5,
            vix_percentile=45.0,
            vix_term_structure=-1.5,
            put_wall_distance_pct=2.5,
            call_wall_distance_pct=3.0,
            net_gex=5e9,
            spx_20d_return=2.5,
            spx_5d_return=0.8,
            spx_distance_from_high=1.2,
            premium_to_strike_pct=0.095,
            annualized_return=25.0
        )

        # Verify feature creation
        self.assertEqual(features.strike, 5800.0)
        self.assertEqual(features.underlying_price, 5850.0)
        self.assertEqual(features.dte, 1)
        self.assertEqual(features.iv_rank, 55.0)

        # Test array conversion
        if ML_AVAILABLE:
            arr = features.to_array()
            self.assertEqual(len(arr), 15)  # 15 features

        # Test feature names
        names = PrometheusFeatures.feature_names()
        self.assertEqual(len(names), 15)
        self.assertIn('iv_rank', names)
        self.assertIn('vix', names)

    def test_feature_meanings(self):
        """Test feature meanings are defined"""
        meanings = PrometheusFeatures.feature_meanings()
        self.assertEqual(len(meanings), 15)
        self.assertIn('iv_rank', meanings)
        self.assertIn('IV percentile', meanings['iv_rank'])

    def test_outcome_creation(self):
        """Test PrometheusOutcome dataclass"""
        features = PrometheusFeatures(
            trade_date="2024-01-15",
            strike=5800.0,
            underlying_price=5850.0,
            dte=1,
            delta=-0.15,
            premium=5.50,
            iv=0.18,
            iv_rank=55.0,
            vix=18.5,
            vix_percentile=45.0,
            vix_term_structure=-1.5,
            put_wall_distance_pct=2.5,
            call_wall_distance_pct=3.0,
            net_gex=5e9,
            spx_20d_return=2.5,
            spx_5d_return=0.8,
            spx_distance_from_high=1.2,
            premium_to_strike_pct=0.095,
            annualized_return=25.0
        )

        outcome = PrometheusOutcome(
            trade_id="TEST-001",
            features=features,
            outcome="WIN",
            pnl=550.0,
            max_drawdown=-200.0,
            settlement_price=5820.0
        )

        self.assertEqual(outcome.trade_id, "TEST-001")
        self.assertTrue(outcome.is_win())
        self.assertEqual(outcome.pnl, 550.0)

    def test_logger_functionality(self):
        """Test Prometheus logger"""
        self.logger.set_session("test-session")
        trace_id = self.logger.new_trace()

        self.assertIsNotNone(trace_id)

        # Log a test entry
        self.logger.log(
            LogType.INFO,
            "TEST_LOG",
            "This is a test log entry",
            details={'test': True}
        )

        # Get logs from memory
        logs = self.logger.get_logs(limit=10)
        self.assertGreater(len(logs), 0)

        # Verify log entry
        last_log = logs[-1]
        self.assertEqual(last_log['action'], 'TEST_LOG')
        self.assertEqual(last_log['log_type'], 'INFO')

    def test_prediction_without_model(self):
        """Test prediction when model is not trained"""
        # Create a new trainer without loading model
        trainer = PrometheusMLTrainer(model_path="/tmp/nonexistent_model.pkl")

        features = PrometheusFeatures(
            trade_date="2024-01-15",
            strike=5800.0,
            underlying_price=5850.0,
            dte=1,
            delta=-0.15,
            premium=5.50,
            iv=0.18,
            iv_rank=55.0,
            vix=18.5,
            vix_percentile=45.0,
            vix_term_structure=-1.5,
            put_wall_distance_pct=2.5,
            call_wall_distance_pct=3.0,
            net_gex=5e9,
            spx_20d_return=2.5,
            spx_5d_return=0.8,
            spx_distance_from_high=1.2,
            premium_to_strike_pct=0.095,
            annualized_return=25.0
        )

        prediction = trainer.predict(features)

        # Without a trained model, should return neutral recommendation
        self.assertEqual(prediction.recommendation, Recommendation.NEUTRAL)
        self.assertEqual(prediction.win_probability, 0.0)
        self.assertIn('not trained', prediction.reasoning.lower())

    @unittest.skipUnless(ML_AVAILABLE, "ML libraries not available")
    def test_training_with_insufficient_data(self):
        """Test training fails with insufficient data"""
        trainer = PrometheusMLTrainer(model_path="/tmp/test_model.pkl")

        # Create only 5 outcomes (below minimum of 30)
        outcomes = []
        for i in range(5):
            features = PrometheusFeatures(
                trade_date=f"2024-01-{i+1:02d}",
                strike=5800.0,
                underlying_price=5850.0,
                dte=1,
                delta=-0.15,
                premium=5.50,
                iv=0.18,
                iv_rank=55.0,
                vix=18.5,
                vix_percentile=45.0,
                vix_term_structure=-1.5,
                put_wall_distance_pct=2.5,
                call_wall_distance_pct=3.0,
                net_gex=5e9,
                spx_20d_return=2.5,
                spx_5d_return=0.8,
                spx_distance_from_high=1.2,
                premium_to_strike_pct=0.095,
                annualized_return=25.0
            )
            outcomes.append(PrometheusOutcome(
                trade_id=f"TEST-{i:03d}",
                features=features,
                outcome="WIN" if i % 2 == 0 else "LOSS",
                pnl=550.0 if i % 2 == 0 else -800.0,
                max_drawdown=-200.0,
                settlement_price=5820.0
            ))

        result = trainer.train(outcomes, min_samples=30)

        self.assertIn('error', result)
        self.assertIn('30', result['error'])

    @unittest.skipUnless(ML_AVAILABLE, "ML libraries not available")
    def test_training_workflow(self):
        """Test full training workflow with synthetic data"""
        import numpy as np
        np.random.seed(42)

        trainer = PrometheusMLTrainer(model_path="/tmp/test_prometheus_model.pkl")

        # Generate 50 synthetic outcomes
        outcomes = []
        for i in range(50):
            # Create features with some pattern
            iv_rank = np.random.uniform(20, 80)
            vix = np.random.uniform(12, 35)

            # Simple pattern: higher IV rank + moderate VIX = higher win rate
            win_prob = 0.5 + (iv_rank - 50) * 0.005 + (25 - abs(vix - 22)) * 0.01
            is_win = np.random.random() < win_prob

            features = PrometheusFeatures(
                trade_date=f"2024-{(i // 30) + 1:02d}-{(i % 28) + 1:02d}",
                strike=5800.0 + np.random.uniform(-100, 100),
                underlying_price=5850.0,
                dte=np.random.randint(0, 3),
                delta=-np.random.uniform(0.10, 0.25),
                premium=np.random.uniform(3.0, 8.0),
                iv=np.random.uniform(0.12, 0.25),
                iv_rank=iv_rank,
                vix=vix,
                vix_percentile=np.random.uniform(30, 70),
                vix_term_structure=np.random.uniform(-3, 3),
                put_wall_distance_pct=np.random.uniform(1, 5),
                call_wall_distance_pct=np.random.uniform(1, 5),
                net_gex=np.random.uniform(-5e9, 10e9),
                spx_20d_return=np.random.uniform(-5, 5),
                spx_5d_return=np.random.uniform(-3, 3),
                spx_distance_from_high=np.random.uniform(0, 5),
                premium_to_strike_pct=np.random.uniform(0.05, 0.15),
                annualized_return=np.random.uniform(10, 40)
            )

            outcomes.append(PrometheusOutcome(
                trade_id=f"SYNTH-{i:03d}",
                features=features,
                outcome="WIN" if is_win else "LOSS",
                pnl=550.0 if is_win else -800.0,
                max_drawdown=np.random.uniform(-500, 0),
                settlement_price=features.strike + np.random.uniform(-50, 50)
            ))

        # Train the model
        result = trainer.train(outcomes, min_samples=30, calibrate=True)

        # Verify training succeeded
        self.assertTrue(result.get('success', False), f"Training failed: {result}")
        self.assertIsNotNone(trainer.model)
        self.assertIsNotNone(trainer.model_version)

        # Verify metrics
        metrics = result.get('metrics', {})
        self.assertIn('accuracy', metrics)
        self.assertIn('cv_accuracy_mean', metrics)
        self.assertIn('feature_importance', metrics)

        # Verify feature importance
        importance = trainer.get_feature_importance_analysis()
        self.assertIn('features', importance)
        self.assertEqual(len(importance['features']), 15)

    @unittest.skipUnless(ML_AVAILABLE, "ML libraries not available")
    def test_prediction_with_trained_model(self):
        """Test prediction after training"""
        import numpy as np
        np.random.seed(42)

        trainer = PrometheusMLTrainer(model_path="/tmp/test_pred_model.pkl")

        # Generate training data
        outcomes = []
        for i in range(40):
            features = PrometheusFeatures(
                trade_date=f"2024-01-{(i % 28) + 1:02d}",
                strike=5800.0,
                underlying_price=5850.0,
                dte=1,
                delta=-0.15,
                premium=5.50,
                iv=0.18,
                iv_rank=50.0 + np.random.uniform(-20, 20),
                vix=18.5 + np.random.uniform(-5, 10),
                vix_percentile=45.0,
                vix_term_structure=np.random.uniform(-2, 2),
                put_wall_distance_pct=2.5,
                call_wall_distance_pct=3.0,
                net_gex=5e9,
                spx_20d_return=np.random.uniform(-2, 2),
                spx_5d_return=np.random.uniform(-1, 1),
                spx_distance_from_high=np.random.uniform(0, 3),
                premium_to_strike_pct=0.095,
                annualized_return=25.0
            )
            outcomes.append(PrometheusOutcome(
                trade_id=f"TRAIN-{i:03d}",
                features=features,
                outcome="WIN" if i % 3 != 0 else "LOSS",
                pnl=550.0 if i % 3 != 0 else -800.0,
                max_drawdown=-200.0,
                settlement_price=5820.0
            ))

        # Train
        result = trainer.train(outcomes, calibrate=True)
        self.assertTrue(result.get('success', False))

        # Now predict on new features
        new_features = PrometheusFeatures(
            trade_date="2024-02-01",
            strike=5800.0,
            underlying_price=5850.0,
            dte=1,
            delta=-0.15,
            premium=5.50,
            iv=0.18,
            iv_rank=65.0,  # High IV rank - should be favorable
            vix=20.0,
            vix_percentile=50.0,
            vix_term_structure=-1.0,  # Contango - favorable
            put_wall_distance_pct=2.0,  # Close support
            call_wall_distance_pct=3.0,
            net_gex=5e9,
            spx_20d_return=1.0,
            spx_5d_return=0.5,
            spx_distance_from_high=1.0,
            premium_to_strike_pct=0.095,
            annualized_return=28.0  # Good premium
        )

        prediction = trainer.predict(new_features, trade_id="PRED-001")

        # Verify prediction structure
        self.assertIsNotNone(prediction.win_probability)
        self.assertIsInstance(prediction.recommendation, Recommendation)
        self.assertIsNotNone(prediction.reasoning)
        self.assertIn('positive', prediction.key_factors)

        # Verify probability is valid
        self.assertGreaterEqual(prediction.win_probability, 0.0)
        self.assertLessEqual(prediction.win_probability, 1.0)


class TestPrometheusAPI(unittest.TestCase):
    """Test Prometheus API endpoints"""

    API_BASE = os.getenv("API_BASE_URL", "http://localhost:8000")

    def setUp(self):
        """Set up test fixtures"""
        if not REQUESTS_AVAILABLE:
            self.skipTest("requests library not available")

    def test_health_endpoint(self):
        """Test health check endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/health", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('status', data)
            self.assertIn('prometheus_available', data)
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_status_endpoint(self):
        """Test status endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/status", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('ml_library_available', data)
            self.assertIn('model_trained', data)
            self.assertIn('honest_assessment', data)
            self.assertIn('what_ml_can_do', data)
            self.assertIn('what_ml_cannot_do', data)
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_feature_importance_endpoint(self):
        """Test feature importance endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/feature-importance", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('data', data)
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_logs_endpoint(self):
        """Test logs endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/logs?limit=10", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('data', data)
            self.assertIn('logs', data['data'])
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_predict_endpoint(self):
        """Test prediction endpoint"""
        try:
            payload = {
                "trade_date": "2024-01-15",
                "strike": 5800.0,
                "underlying_price": 5850.0,
                "dte": 1,
                "delta": -0.15,
                "premium": 5.50,
                "iv": 0.18,
                "iv_rank": 55.0,
                "vix": 18.5,
                "vix_percentile": 45.0,
                "vix_term_structure": -1.5,
                "put_wall_distance_pct": 2.5,
                "call_wall_distance_pct": 3.0,
                "net_gex": 5e9,
                "spx_20d_return": 2.5,
                "spx_5d_return": 0.8,
                "spx_distance_from_high": 1.2,
                "premium_to_strike_pct": 0.095,
                "annualized_return": 25.0
            }

            response = requests.post(
                f"{self.API_BASE}/api/prometheus/predict",
                json=payload,
                timeout=5
            )
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('data', data)
            self.assertIn('win_probability', data['data'])
            self.assertIn('recommendation', data['data'])
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_training_history_endpoint(self):
        """Test training history endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/training-history", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('data', data)
            self.assertIn('history', data['data'])
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")

    def test_performance_endpoint(self):
        """Test performance metrics endpoint"""
        try:
            response = requests.get(f"{self.API_BASE}/api/prometheus/performance", timeout=5)
            self.assertEqual(response.status_code, 200)

            data = response.json()
            self.assertIn('success', data)
            self.assertIn('data', data)
        except requests.exceptions.ConnectionError:
            self.skipTest("API server not running")


class TestPrometheusDatabaseIntegration(unittest.TestCase):
    """Test Prometheus database integration"""

    def setUp(self):
        """Set up test fixtures"""
        if not PROMETHEUS_AVAILABLE or not DB_AVAILABLE:
            self.skipTest("Prometheus ML or database not available")

    def test_log_persistence(self):
        """Test that logs are persisted to database"""
        logger = get_prometheus_logger()
        logger.set_session(f"test-{uuid.uuid4().hex[:8]}")

        # Log an entry
        logger.log(
            LogType.INFO,
            "DB_PERSISTENCE_TEST",
            "Testing database persistence",
            details={'test_id': uuid.uuid4().hex}
        )

        # Give time for async persistence
        time.sleep(0.5)

        # Check if retrievable from DB
        logs = logger.get_logs_from_db(limit=10, log_type='INFO')
        self.assertIsInstance(logs, list)

    def test_model_db_persistence(self):
        """Test model persistence to database"""
        if not ML_AVAILABLE:
            self.skipTest("ML libraries not available")

        import numpy as np
        np.random.seed(42)

        trainer = PrometheusMLTrainer(model_path="/tmp/test_db_persist.pkl")

        # Generate minimal training data
        outcomes = []
        for i in range(35):
            features = PrometheusFeatures(
                trade_date=f"2024-01-{(i % 28) + 1:02d}",
                strike=5800.0,
                underlying_price=5850.0,
                dte=1,
                delta=-0.15,
                premium=5.50,
                iv=0.18,
                iv_rank=50.0 + np.random.uniform(-20, 20),
                vix=18.5,
                vix_percentile=45.0,
                vix_term_structure=0.0,
                put_wall_distance_pct=2.5,
                call_wall_distance_pct=3.0,
                net_gex=5e9,
                spx_20d_return=0.0,
                spx_5d_return=0.0,
                spx_distance_from_high=1.0,
                premium_to_strike_pct=0.095,
                annualized_return=25.0
            )
            outcomes.append(PrometheusOutcome(
                trade_id=f"DBTEST-{i:03d}",
                features=features,
                outcome="WIN" if i % 2 == 0 else "LOSS",
                pnl=550.0 if i % 2 == 0 else -800.0,
                max_drawdown=-200.0,
                settlement_price=5820.0
            ))

        # Train and save
        result = trainer.train(outcomes, calibrate=False)

        if result.get('success'):
            # Model should be saved to DB
            self.assertIsNotNone(trainer.model_version)

            # Try loading from DB
            new_trainer = PrometheusMLTrainer(model_path="/tmp/nonexistent_test.pkl")
            loaded = new_trainer._load_from_db()

            # If DB available and model was saved, should load
            # (may not work if tables don't exist)
            if loaded:
                self.assertIsNotNone(new_trainer.model)


def run_all_tests():
    """Run all Prometheus tests"""
    print("=" * 60)
    print("PROMETHEUS End-to-End Tests")
    print("=" * 60)
    print(f"Prometheus Available: {PROMETHEUS_AVAILABLE}")
    print(f"ML Available: {ML_AVAILABLE if PROMETHEUS_AVAILABLE else 'N/A'}")
    print(f"DB Available: {DB_AVAILABLE if PROMETHEUS_AVAILABLE else 'N/A'}")
    print(f"Requests Available: {REQUESTS_AVAILABLE}")
    print("=" * 60)
    print()

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPrometheusML))
    suite.addTests(loader.loadTestsFromTestCase(TestPrometheusAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestPrometheusDatabaseIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Summary
    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped)}")
    print(f"Success: {result.wasSuccessful()}")
    print("=" * 60)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
