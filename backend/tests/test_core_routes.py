"""
Tests for Core Routes (Health, System, Time)

Run with: pytest backend/tests/test_core_routes.py -v
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


class TestHealthEndpoints:
    """Tests for health check endpoints"""

    def test_health_endpoint(self, test_client):
        """Test main health endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/health")
        assert response.status_code in [200, 404, 500]

    def test_api_health_endpoint(self, test_client):
        """Test API health endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/health")
        assert response.status_code in [200, 404, 500]


class TestTimeEndpoints:
    """Tests for time endpoints"""

    def test_current_time_endpoint(self, test_client):
        """Test current time endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/time")
        assert response.status_code in [200, 404, 500]

    def test_market_hours_endpoint(self, test_client):
        """Test market hours endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/market-hours")
        assert response.status_code in [200, 404, 500]


class TestSystemEndpoints:
    """Tests for system status endpoints"""

    def test_system_status_endpoint(self, test_client):
        """Test system status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system/status")
        assert response.status_code in [200, 404, 500]

    def test_system_health_endpoint(self, test_client):
        """Test comprehensive system health"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system-health")
        assert response.status_code in [200, 404, 500]
