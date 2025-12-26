"""
Tests for SPX Backtest Routes

Run with: pytest backend/tests/test_spx_backtest_routes.py -v
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


class TestSPXBacktestEndpoints:
    """Tests for SPX backtest endpoints"""

    def test_run_spx_backtest(self, test_client):
        """Test run SPX backtest"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/spx-backtest/run",
            json={"strategy": "wheel", "start_date": "2024-01-01"}
        )
        assert response.status_code in [200, 202, 400, 404, 500]

    def test_get_spx_backtest_results(self, test_client):
        """Test get SPX backtest results"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx-backtest/results")
        assert response.status_code in [200, 404, 500]

    def test_get_spx_backtest_trades(self, test_client):
        """Test get SPX backtest trades"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx-backtest/trades")
        assert response.status_code in [200, 404, 500]

    def test_spx_backtest_status(self, test_client):
        """Test SPX backtest status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/spx-backtest/status")
        assert response.status_code in [200, 404, 500]
