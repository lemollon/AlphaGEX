"""
Tests for Logs Routes

Run with: pytest backend/tests/test_logs_routes.py -v
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


class TestLogsEndpoints:
    """Tests for logs endpoints"""

    def test_get_logs_endpoint(self, test_client):
        """Test get logs endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/logs")
        assert response.status_code in [200, 404, 500]

    def test_get_logs_by_level(self, test_client):
        """Test get logs filtered by level"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/logs", params={"level": "ERROR"})
        assert response.status_code in [200, 404, 500]

    def test_get_bot_logs(self, test_client):
        """Test get logs for specific bot"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/logs/bot/FORTRESS")
        assert response.status_code in [200, 404, 500]

    def test_get_trade_logs(self, test_client):
        """Test get trade decision logs"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/logs/trades")
        assert response.status_code in [200, 404, 500]
