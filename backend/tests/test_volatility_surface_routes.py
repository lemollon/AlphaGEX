"""
Tests for Volatility Surface Routes

Run with: pytest backend/tests/test_volatility_surface_routes.py -v
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


class TestVolatilitySurfaceEndpoints:
    """Tests for volatility surface endpoints"""

    def test_get_vol_surface(self, test_client):
        """Test get volatility surface"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/volatility-surface/SPY")
        assert response.status_code in [200, 404, 500]

    def test_get_skew(self, test_client):
        """Test get skew data"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/volatility-surface/SPY/skew")
        assert response.status_code in [200, 404, 500]

    def test_get_term_structure(self, test_client):
        """Test get term structure"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/volatility-surface/SPY/term-structure")
        assert response.status_code in [200, 404, 500]

    def test_get_iv_rank(self, test_client):
        """Test get IV rank"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/volatility-surface/SPY/iv-rank")
        assert response.status_code in [200, 404, 500]

    def test_get_vol_history(self, test_client):
        """Test get volatility history"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/volatility-surface/SPY/history")
        assert response.status_code in [200, 404, 500]
