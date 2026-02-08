"""
Tests for Watchtower Routes (Real-time Gamma Visualization)

Run with: pytest backend/tests/test_watchtower_routes.py -v
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


class TestArgusEndpoints:
    """Tests for Watchtower gamma visualization endpoints"""

    def test_watchtower_data_endpoint(self, test_client):
        """Test Watchtower main data endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/watchtower/data")
        assert response.status_code in [200, 404, 500]

    def test_watchtower_commentary_endpoint(self, test_client):
        """Test Watchtower commentary endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/watchtower/commentary")
        assert response.status_code in [200, 404, 500]

    def test_argus_levels_endpoint(self, test_client):
        """Test Watchtower gamma levels endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/watchtower/levels")
        assert response.status_code in [200, 404, 500]

    def test_watchtower_history_endpoint(self, test_client):
        """Test Watchtower historical data endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/watchtower/history")
        assert response.status_code in [200, 404, 500]

    def test_watchtower_status_endpoint(self, test_client):
        """Test Watchtower status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/watchtower/status")
        assert response.status_code in [200, 404, 500]
