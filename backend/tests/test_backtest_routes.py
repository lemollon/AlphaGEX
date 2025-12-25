"""
Backtest Routes Tests

Tests for backtesting API endpoints.

Run with: pytest backend/tests/test_backtest_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestBacktestResultsEndpoint:
    """Tests for /api/backtest/results endpoint"""

    def test_get_results_success(self):
        """Test backtest results endpoint"""
        response = client.get("/api/backtest/results")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestBacktestStrategiesEndpoint:
    """Tests for /api/backtest/strategies endpoint"""

    def test_get_strategies_success(self):
        """Test strategies endpoint"""
        response = client.get("/api/backtest/strategies")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestBacktestHistoryEndpoint:
    """Tests for /api/backtest/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/backtest/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestBacktestTradesEndpoint:
    """Tests for /api/backtest/trades endpoint"""

    def test_get_trades_success(self):
        """Test trades endpoint"""
        response = client.get("/api/backtest/trades")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestBacktestMetricsEndpoint:
    """Tests for /api/backtest/metrics endpoint"""

    def test_get_metrics_success(self):
        """Test metrics endpoint"""
        response = client.get("/api/backtest/metrics")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
