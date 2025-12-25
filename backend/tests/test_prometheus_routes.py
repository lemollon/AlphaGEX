"""
Prometheus ML Routes Tests

Tests for Prometheus ML API endpoints.

Run with: pytest backend/tests/test_prometheus_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestPrometheusStatusEndpoint:
    """Tests for /api/prometheus/status endpoint"""

    def test_get_status_success(self):
        """Test status endpoint"""
        response = client.get("/api/prometheus/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPrometheusPredictionEndpoint:
    """Tests for /api/prometheus/prediction endpoint"""

    def test_get_prediction_success(self):
        """Test prediction endpoint"""
        response = client.get("/api/prometheus/prediction")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPrometheusPerformanceEndpoint:
    """Tests for /api/prometheus/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint"""
        response = client.get("/api/prometheus/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPrometheusSignalsEndpoint:
    """Tests for /api/prometheus/signals endpoint"""

    def test_get_signals_success(self):
        """Test signals endpoint"""
        response = client.get("/api/prometheus/signals")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
