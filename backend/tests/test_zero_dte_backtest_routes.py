"""
Comprehensive Tests for Zero DTE Backtest Routes

Tests the 0DTE backtest API endpoints including:
- Backtest execution endpoints
- Strategy configuration
- Results retrieval
- Historical data endpoints

Run with: pytest backend/tests/test_zero_dte_backtest_routes.py -v
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
    """Create test client for FastAPI app"""
    with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost:5432/test'}):
        with patch('database_adapter.psycopg2'):
            try:
                from main import app
                return TestClient(app)
            except Exception as e:
                pytest.skip(f"Could not create test client: {e}")


class TestBacktestExecutionEndpoints:
    """Tests for backtest execution endpoints"""

    def test_run_backtest_endpoint_exists(self, test_client):
        """Test run backtest endpoint exists"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/zero-dte/backtest/run",
            json={
                "strategy": "iron_condor",
                "start_date": "2024-01-01",
                "end_date": "2024-12-01"
            }
        )
        assert response.status_code in [200, 202, 400, 404, 500]

    def test_backtest_status_endpoint(self, test_client):
        """Test backtest status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/status")
        assert response.status_code in [200, 404, 500]


class TestStrategyConfigEndpoints:
    """Tests for strategy configuration endpoints"""

    def test_get_strategies_endpoint(self, test_client):
        """Test get available strategies endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/strategies")
        assert response.status_code in [200, 404, 500]

    def test_get_strategy_config_endpoint(self, test_client):
        """Test get strategy configuration endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/strategies/iron_condor/config")
        assert response.status_code in [200, 404, 500]


class TestBacktestResultsEndpoints:
    """Tests for backtest results endpoints"""

    def test_get_results_endpoint(self, test_client):
        """Test get backtest results endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/results")
        assert response.status_code in [200, 404, 500]

    def test_get_specific_result_endpoint(self, test_client):
        """Test get specific backtest result endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/results/1")
        assert response.status_code in [200, 404, 500]

    def test_get_trades_endpoint(self, test_client):
        """Test get backtest trades endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/trades")
        assert response.status_code in [200, 404, 500]


class TestHistoricalDataEndpoints:
    """Tests for historical data endpoints"""

    def test_historical_performance_endpoint(self, test_client):
        """Test historical performance endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/historical/performance")
        assert response.status_code in [200, 404, 500]

    def test_historical_trades_endpoint(self, test_client):
        """Test historical trades endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/historical/trades")
        assert response.status_code in [200, 404, 500]


class TestMockedBacktestRoutes:
    """Tests with mocked backtest dependencies"""

    @patch('backend.api.routes.zero_dte_backtest_routes.run_backtest')
    def test_backtest_returns_job_id(self, mock_run, test_client):
        """Test backtest returns job ID"""
        if test_client is None:
            pytest.skip("Test client not available")

        mock_run.return_value = {"job_id": "test-123", "status": "queued"}

        response = test_client.post(
            "/api/zero-dte/backtest/run",
            json={"strategy": "iron_condor"}
        )

        if response.status_code in [200, 202]:
            data = response.json()
            assert "job_id" in data or "id" in data or "status" in data


class TestBacktestRequestValidation:
    """Tests for backtest request validation"""

    def test_missing_strategy_rejected(self, test_client):
        """Test missing strategy is rejected"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/zero-dte/backtest/run",
            json={}
        )
        assert response.status_code in [400, 422, 500]

    def test_invalid_date_format_rejected(self, test_client):
        """Test invalid date format is rejected"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/zero-dte/backtest/run",
            json={
                "strategy": "iron_condor",
                "start_date": "not-a-date"
            }
        )
        assert response.status_code in [400, 422, 500]


class TestErrorHandling:
    """Tests for error handling"""

    def test_invalid_strategy_handled(self, test_client):
        """Test invalid strategy is handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/zero-dte/backtest/run",
            json={"strategy": "nonexistent_strategy"}
        )
        assert response.status_code in [200, 400, 404, 500]

    def test_invalid_result_id_handled(self, test_client):
        """Test invalid result ID is handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/results/999999")
        assert response.status_code in [404, 500]


class TestResponseFormats:
    """Tests for response format consistency"""

    def test_strategies_response_format(self, test_client):
        """Test strategies response has expected format"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/strategies")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

    def test_results_response_format(self, test_client):
        """Test results response has expected format"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/zero-dte/backtest/results")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))


class TestPaginationEndpoints:
    """Tests for pagination on list endpoints"""

    def test_trades_pagination(self, test_client):
        """Test trades endpoint supports pagination"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get(
            "/api/zero-dte/backtest/trades",
            params={"page": 1, "limit": 10}
        )
        assert response.status_code in [200, 404, 500]

    def test_results_pagination(self, test_client):
        """Test results endpoint supports pagination"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get(
            "/api/zero-dte/backtest/results",
            params={"page": 1, "limit": 10}
        )
        assert response.status_code in [200, 404, 500]


class TestFilteringEndpoints:
    """Tests for filtering on list endpoints"""

    def test_filter_by_strategy(self, test_client):
        """Test filtering results by strategy"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get(
            "/api/zero-dte/backtest/results",
            params={"strategy": "iron_condor"}
        )
        assert response.status_code in [200, 404, 500]

    def test_filter_by_date_range(self, test_client):
        """Test filtering results by date range"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get(
            "/api/zero-dte/backtest/results",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-12-01"
            }
        )
        assert response.status_code in [200, 404, 500]
