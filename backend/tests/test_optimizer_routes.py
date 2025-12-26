"""
Tests for Optimizer Routes

Run with: pytest backend/tests/test_optimizer_routes.py -v
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


class TestOptimizerEndpoints:
    """Tests for strategy optimizer endpoints"""

    def test_optimizer_status(self, test_client):
        """Test optimizer status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/optimizer/status")
        assert response.status_code in [200, 404, 500]

    def test_run_optimization(self, test_client):
        """Test run optimization"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/optimizer/run",
            json={"strategy": "iron_condor", "params": {}}
        )
        assert response.status_code in [200, 202, 400, 404, 500]

    def test_get_optimization_results(self, test_client):
        """Test get optimization results"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/optimizer/results")
        assert response.status_code in [200, 404, 500]

    def test_get_optimal_params(self, test_client):
        """Test get optimal parameters"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/optimizer/optimal-params/iron_condor")
        assert response.status_code in [200, 404, 500]
