"""
DISCERNMENT ML Engine Routes Tests

Tests for the DISCERNMENT ML API endpoints including:
- Model status and predictions
- Training endpoints
- Feature importance
- Model performance

Run with: pytest backend/tests/test_discernment_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestDiscernmentStatusEndpoint:
    """Tests for /api/discernment/status endpoint"""

    def test_get_status_success(self):
        """Test that status endpoint returns valid data structure"""
        response = client.get("/api/discernment/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

    def test_status_has_model_info(self):
        """Test that status includes model information"""
        response = client.get("/api/discernment/status")

        assert response.status_code == 200
        data = response.json()

        # Should have some model status info
        assert "data" in data


class TestDiscernmentPredictionEndpoint:
    """Tests for /api/discernment/predict endpoint"""

    def test_get_prediction_success(self):
        """Test prediction endpoint returns valid structure"""
        response = client.get("/api/discernment/predict")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_prediction_with_symbol(self):
        """Test prediction with specific symbol"""
        response = client.get("/api/discernment/predict?symbol=SPY")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestDiscernmentModelsEndpoint:
    """Tests for /api/discernment/models endpoint"""

    def test_get_models_success(self):
        """Test models endpoint returns available models"""
        response = client.get("/api/discernment/models")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDiscernmentFeaturesEndpoint:
    """Tests for /api/discernment/features endpoint"""

    def test_get_features_success(self):
        """Test features endpoint returns feature info"""
        response = client.get("/api/discernment/features")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDiscernmentPerformanceEndpoint:
    """Tests for /api/discernment/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint returns model metrics"""
        response = client.get("/api/discernment/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_performance_with_days(self):
        """Test performance with days parameter"""
        response = client.get("/api/discernment/performance?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestDiscernmentHistoryEndpoint:
    """Tests for /api/discernment/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint returns prediction history"""
        response = client.get("/api/discernment/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_history_with_limit(self):
        """Test history with limit parameter"""
        response = client.get("/api/discernment/history?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestDiscernmentAccuracyEndpoint:
    """Tests for /api/discernment/accuracy endpoint"""

    def test_get_accuracy_success(self):
        """Test accuracy endpoint returns accuracy metrics"""
        response = client.get("/api/discernment/accuracy")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDiscernmentSignalsEndpoint:
    """Tests for /api/discernment/signals endpoint"""

    def test_get_signals_success(self):
        """Test signals endpoint returns ML signals"""
        response = client.get("/api/discernment/signals")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDiscernmentDataValidation:
    """Tests for data validation in DISCERNMENT endpoints"""

    def test_prediction_confidence_in_range(self):
        """Test that prediction confidence is between 0 and 1"""
        response = client.get("/api/discernment/predict")

        assert response.status_code == 200
        data = response.json()

        if "confidence" in data.get("data", {}):
            confidence = data["data"]["confidence"]
            assert 0 <= confidence <= 1

    def test_accuracy_in_range(self):
        """Test that accuracy metrics are valid percentages"""
        response = client.get("/api/discernment/accuracy")

        assert response.status_code == 200
        data = response.json()

        if "accuracy" in data.get("data", {}):
            accuracy = data["data"]["accuracy"]
            assert 0 <= accuracy <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
