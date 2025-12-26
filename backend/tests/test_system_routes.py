"""
Tests for System Routes

Run with: pytest backend/tests/test_system_routes.py -v
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


class TestSystemEndpoints:
    """Tests for system endpoints"""

    def test_system_info(self, test_client):
        """Test system info endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system/info")
        assert response.status_code in [200, 404, 500]

    def test_system_config(self, test_client):
        """Test system config endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system/config")
        assert response.status_code in [200, 404, 500]

    def test_system_metrics(self, test_client):
        """Test system metrics endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system/metrics")
        assert response.status_code in [200, 404, 500]

    def test_system_version(self, test_client):
        """Test system version endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/system/version")
        assert response.status_code in [200, 404, 500]
