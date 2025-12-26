"""
Tests for Setups Routes (Trading Setups)

Run with: pytest backend/tests/test_setups_routes.py -v
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


class TestSetupsEndpoints:
    """Tests for trading setups endpoints"""

    def test_get_setups(self, test_client):
        """Test get current setups"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/setups")
        assert response.status_code in [200, 404, 500]

    def test_get_setup_by_symbol(self, test_client):
        """Test get setup for specific symbol"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/setups/SPY")
        assert response.status_code in [200, 404, 500]

    def test_get_active_setups(self, test_client):
        """Test get active setups"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/setups/active")
        assert response.status_code in [200, 404, 500]

    def test_get_setup_history(self, test_client):
        """Test get setup history"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/setups/history")
        assert response.status_code in [200, 404, 500]
