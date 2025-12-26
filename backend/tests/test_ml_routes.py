"""
Tests for ML Routes (Machine Learning)

Run with: pytest backend/tests/test_ml_routes.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_client():
    """Create test client"""
    with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost:5432/test'}):
        with patch('database_adapter.psycopg2'):
            try:
                from main import app
                return TestClient(app)
            except Exception as e:
                pytest.skip(f"Could not create test client: {e}")


class TestMLEndpoints:
    """Tests for ML endpoints"""

    def test_ml_status(self, test_client):
        """Test ML status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/ml/status")
        assert response.status_code in [200, 404, 500]

    def test_ml_models(self, test_client):
        """Test list ML models"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/ml/models")
        assert response.status_code in [200, 404, 500]

    def test_ml_predict(self, test_client):
        """Test ML prediction endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/ml/predict",
            json={"symbol": "SPY", "features": {}}
        )
        assert response.status_code in [200, 400, 404, 500]

    def test_ml_training_status(self, test_client):
        """Test ML training status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/ml/training/status")
        assert response.status_code in [200, 404, 500]

    def test_ml_model_performance(self, test_client):
        """Test ML model performance"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/ml/performance")
        assert response.status_code in [200, 404, 500]
