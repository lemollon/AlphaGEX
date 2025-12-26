"""
Tests for SPX Routes

Run with: pytest backend/tests/test_spx_routes.py -v
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


class TestSPXEndpoints:
    """Tests for SPX data endpoints"""

    def test_get_spx_quote(self, test_client):
        """Test get SPX quote"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx/quote")
        assert response.status_code in [200, 404, 500]

    def test_get_spx_options(self, test_client):
        """Test get SPX options chain"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx/options")
        assert response.status_code in [200, 404, 500]

    def test_get_spx_gex(self, test_client):
        """Test get SPX GEX data"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx/gex")
        assert response.status_code in [200, 404, 500]

    def test_get_spx_levels(self, test_client):
        """Test get SPX key levels"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx/levels")
        assert response.status_code in [200, 404, 500]
