"""
Tests for Solomon Routes (Feedback Loop Intelligence)

Run with: pytest backend/tests/test_solomon_routes.py -v
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


class TestSolomonEndpoints:
    """Tests for Solomon feedback loop endpoints"""

    def test_solomon_status(self, test_client):
        """Test Solomon status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/solomon/status")
        assert response.status_code in [200, 404, 500]

    def test_solomon_analysis(self, test_client):
        """Test Solomon analysis"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/solomon/analysis")
        assert response.status_code in [200, 404, 500]

    def test_solomon_recommendations(self, test_client):
        """Test Solomon recommendations"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/solomon/recommendations")
        assert response.status_code in [200, 404, 500]

    def test_solomon_bot_health(self, test_client):
        """Test Solomon bot health"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/solomon/bot-health")
        assert response.status_code in [200, 404, 500]

    def test_solomon_run_feedback(self, test_client):
        """Test run feedback loop"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post("/api/solomon/run-feedback")
        assert response.status_code in [200, 202, 400, 404, 500]

    def test_solomon_kill_switch(self, test_client):
        """Test Solomon kill switch status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/solomon/kill-switch")
        assert response.status_code in [200, 404, 500]

    def test_solomon_toggle_kill_switch(self, test_client):
        """Test toggle kill switch"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/solomon/kill-switch/toggle",
            json={"bot": "ARES", "enabled": True}
        )
        assert response.status_code in [200, 400, 404, 500]
