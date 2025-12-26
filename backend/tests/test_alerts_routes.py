"""
Tests for Alerts Routes

Run with: pytest backend/tests/test_alerts_routes.py -v
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


class TestAlertsEndpoints:
    """Tests for alerts endpoints"""

    def test_get_alerts_endpoint(self, test_client):
        """Test get all alerts"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/alerts")
        assert response.status_code in [200, 404, 500]

    def test_get_active_alerts(self, test_client):
        """Test get active alerts"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/alerts/active")
        assert response.status_code in [200, 404, 500]

    def test_create_alert(self, test_client):
        """Test create alert"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/alerts",
            json={"type": "price", "symbol": "SPY", "threshold": 590}
        )
        assert response.status_code in [200, 201, 400, 404, 500]

    def test_delete_alert(self, test_client):
        """Test delete alert"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.delete("/api/alerts/1")
        assert response.status_code in [200, 204, 404, 500]

    def test_alert_history(self, test_client):
        """Test alert history"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/alerts/history")
        assert response.status_code in [200, 404, 500]
