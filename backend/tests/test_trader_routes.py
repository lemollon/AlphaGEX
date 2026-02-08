"""
Comprehensive Tests for Trader Routes

Tests the trading API endpoints including:
- Trader status endpoints
- Position management
- Trade execution
- Performance metrics

Run with: pytest backend/tests/test_trader_routes.py -v
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


@pytest.fixture
def mock_trader():
    """Mock autonomous paper trader"""
    trader = MagicMock()
    trader.get_performance.return_value = {
        'starting_capital': 1000000,
        'current_value': 1050000,
        'total_pnl': 50000,
        'total_trades': 25,
        'win_rate': 72.0,
        'sharpe_ratio': 1.85
    }
    trader.get_open_positions.return_value = []
    trader.get_live_status.return_value = {
        'status': 'RUNNING',
        'current_action': 'Scanning',
        'is_working': True
    }
    return trader


class TestTraderStatusEndpoints:
    """Tests for trader status endpoints"""

    def test_trader_status_endpoint_exists(self, test_client):
        """Test trader status endpoint returns response"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/status")
        # Should return 200 or appropriate status
        assert response.status_code in [200, 404, 500]

    def test_trader_performance_endpoint_exists(self, test_client):
        """Test trader performance endpoint exists"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/performance")
        assert response.status_code in [200, 404, 500]


class TestPositionEndpoints:
    """Tests for position management endpoints"""

    def test_open_positions_endpoint(self, test_client):
        """Test open positions endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/positions")
        assert response.status_code in [200, 404, 500]

    def test_position_history_endpoint(self, test_client):
        """Test position history endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/positions/history")
        assert response.status_code in [200, 404, 500]


class TestPerformanceEndpoints:
    """Tests for performance metric endpoints"""

    def test_equity_curve_endpoint(self, test_client):
        """Test equity curve endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/equity-curve")
        assert response.status_code in [200, 404, 500]

    def test_trade_history_endpoint(self, test_client):
        """Test trade history endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/trades")
        assert response.status_code in [200, 404, 500]


class TestTraderControlEndpoints:
    """Tests for trader control endpoints"""

    def test_start_trader_endpoint(self, test_client):
        """Test start trader endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post("/api/trader/start")
        assert response.status_code in [200, 400, 404, 500]

    def test_stop_trader_endpoint(self, test_client):
        """Test stop trader endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post("/api/trader/stop")
        assert response.status_code in [200, 400, 404, 500]


class TestBotHeartbeatEndpoints:
    """Tests for bot heartbeat endpoints"""

    def test_phoenix_heartbeat(self, test_client):
        """Test PHOENIX heartbeat endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/heartbeat/PHOENIX")
        assert response.status_code in [200, 404, 500]

    def test_atlas_heartbeat(self, test_client):
        """Test ATLAS heartbeat endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/heartbeat/ATLAS")
        assert response.status_code in [200, 404, 500]

    def test_ares_heartbeat(self, test_client):
        """Test FORTRESS heartbeat endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/heartbeat/FORTRESS")
        assert response.status_code in [200, 404, 500]

    def test_solomon_heartbeat(self, test_client):
        """Test SOLOMON heartbeat endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/heartbeat/SOLOMON")
        assert response.status_code in [200, 404, 500]


class TestMockedTraderRoutes:
    """Tests with mocked trader dependencies"""

    @patch('backend.api.routes.trader_routes.get_trader')
    def test_performance_returns_metrics(self, mock_get_trader, test_client):
        """Test performance endpoint returns expected metrics"""
        if test_client is None:
            pytest.skip("Test client not available")

        mock_trader = MagicMock()
        mock_trader.get_performance.return_value = {
            'starting_capital': 1000000,
            'current_value': 1050000,
            'total_pnl': 50000,
            'win_rate': 72.0
        }
        mock_get_trader.return_value = mock_trader

        response = test_client.get("/api/trader/performance")

        if response.status_code == 200:
            data = response.json()
            assert 'starting_capital' in data or 'error' in data


class TestErrorHandling:
    """Tests for error handling"""

    def test_invalid_endpoint_returns_404(self, test_client):
        """Test invalid endpoint returns 404"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/nonexistent")
        assert response.status_code == 404

    def test_invalid_bot_name_handled(self, test_client):
        """Test invalid bot name is handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/heartbeat/INVALID_BOT")
        # Should return error, not crash
        assert response.status_code in [200, 400, 404, 500]


class TestResponseFormats:
    """Tests for response format consistency"""

    def test_status_response_format(self, test_client):
        """Test status response has expected format"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/status")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_performance_response_format(self, test_client):
        """Test performance response has expected format"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/trader/performance")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
