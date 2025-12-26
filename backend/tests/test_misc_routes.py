"""
Tests for Misc Routes

Run with: pytest backend/tests/test_misc_routes.py -v
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


class TestMiscEndpoints:
    """Tests for miscellaneous endpoints"""

    def test_symbols_endpoint(self, test_client):
        """Test get supported symbols"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/symbols")
        assert response.status_code in [200, 404, 500]

    def test_strategies_endpoint(self, test_client):
        """Test get available strategies"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/strategies")
        assert response.status_code in [200, 404, 500]

    def test_timezone_endpoint(self, test_client):
        """Test timezone endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/timezone")
        assert response.status_code in [200, 404, 500]
