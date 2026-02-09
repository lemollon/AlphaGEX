"""
FORTRESS Iron Condor Routes Tests

Tests for the FORTRESS bot API endpoints including:
- Status endpoint
- Positions endpoint
- Performance metrics
- Trade history
- Configuration

Run with: pytest backend/tests/test_fortress_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestFortressStatusEndpoint:
    """Tests for /api/fortress/status endpoint"""

    def test_get_status_success(self):
        """Test that status endpoint returns valid data structure"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

        status_data = data["data"]
        assert "mode" in status_data
        assert "capital" in status_data
        assert "total_pnl" in status_data
        assert "trade_count" in status_data
        assert "win_rate" in status_data
        assert "open_positions" in status_data
        assert "heartbeat" in status_data

    def test_status_has_config(self):
        """Test that status includes configuration"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        if "config" in data["data"]:
            config = data["data"]["config"]
            assert "risk_per_trade" in config or "ticker" in config

    def test_status_has_heartbeat(self):
        """Test that status includes heartbeat info"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        heartbeat = data["data"]["heartbeat"]
        assert "status" in heartbeat
        assert "scan_count_today" in heartbeat


class TestFortressPositionsEndpoint:
    """Tests for /api/fortress/positions endpoint"""

    def test_get_positions_success(self):
        """Test positions endpoint returns valid structure"""
        response = client.get("/api/fortress/positions")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

    def test_get_open_positions(self):
        """Test getting open positions only"""
        response = client.get("/api/fortress/positions?status=open")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_closed_positions(self):
        """Test getting closed positions only"""
        response = client.get("/api/fortress/positions?status=closed")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestFortressPerformanceEndpoint:
    """Tests for /api/fortress/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint returns valid structure"""
        response = client.get("/api/fortress/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_performance_with_days_param(self):
        """Test performance endpoint with days parameter"""
        response = client.get("/api/fortress/performance?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestFortressEquityCurveEndpoint:
    """Tests for /api/fortress/equity endpoint"""

    def test_get_equity_curve_success(self):
        """Test equity curve endpoint"""
        response = client.get("/api/fortress/equity")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_equity_curve_with_days(self):
        """Test equity curve with days parameter"""
        response = client.get("/api/fortress/equity?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestFortressTradesEndpoint:
    """Tests for /api/fortress/trades endpoint"""

    def test_get_trades_success(self):
        """Test trades endpoint returns valid structure"""
        response = client.get("/api/fortress/trades")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_trades_with_limit(self):
        """Test trades endpoint with limit parameter"""
        response = client.get("/api/fortress/trades?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_trades_with_date_range(self):
        """Test trades endpoint with date range"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = client.get(f"/api/fortress/trades?start_date={today}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestFortressConfigEndpoint:
    """Tests for /api/fortress/config endpoint"""

    def test_get_config_success(self):
        """Test config endpoint returns valid structure"""
        response = client.get("/api/fortress/config")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestFortressPresetsEndpoint:
    """Tests for /api/fortress/presets endpoint"""

    def test_get_presets_success(self):
        """Test presets endpoint returns available presets"""
        response = client.get("/api/fortress/presets")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestFortressAnalysisEndpoint:
    """Tests for /api/fortress/analysis endpoint"""

    def test_get_analysis_success(self):
        """Test analysis endpoint returns market analysis"""
        response = client.get("/api/fortress/analysis")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestFortressSignalsEndpoint:
    """Tests for /api/fortress/signals endpoint"""

    def test_get_signals_success(self):
        """Test signals endpoint returns trading signals"""
        response = client.get("/api/fortress/signals")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestFortressLogsEndpoint:
    """Tests for /api/fortress/logs endpoint"""

    def test_get_logs_success(self):
        """Test logs endpoint returns decision logs"""
        response = client.get("/api/fortress/logs")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_logs_with_limit(self):
        """Test logs endpoint with limit parameter"""
        response = client.get("/api/fortress/logs?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestFortressDataValidation:
    """Tests for data validation in FORTRESS endpoints"""

    def test_capital_is_positive(self):
        """Test that capital values are positive"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        capital = data["data"]["capital"]
        assert capital >= 0

    def test_win_rate_in_range(self):
        """Test that win rate is between 0 and 100"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        win_rate = data["data"]["win_rate"]
        assert 0 <= win_rate <= 100

    def test_mode_is_valid(self):
        """Test that mode is paper or live"""
        response = client.get("/api/fortress/status")

        assert response.status_code == 200
        data = response.json()

        mode = data["data"]["mode"]
        assert mode in ["paper", "live"]


class TestFortressErrorHandling:
    """Tests for error handling in FORTRESS endpoints"""

    def test_invalid_status_filter(self):
        """Test handling of invalid status filter"""
        response = client.get("/api/fortress/positions?status=invalid")

        # Should either return 200 with empty data or 400
        assert response.status_code in [200, 400]

    def test_invalid_date_format(self):
        """Test handling of invalid date format"""
        response = client.get("/api/fortress/trades?start_date=not-a-date")

        # Should handle gracefully
        assert response.status_code in [200, 400, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
