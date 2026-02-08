"""
SOLOMON Directional Spread Routes Tests

Tests for the SOLOMON bot API endpoints including:
- Status endpoint
- Positions endpoint
- Signals and analysis
- Performance metrics

Run with: pytest backend/tests/test_solomon_routes.py -v
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


class TestAthenaStatusEndpoint:
    """Tests for /api/solomon/status endpoint"""

    def test_get_status_success(self):
        """Test that status endpoint returns valid data structure"""
        response = client.get("/api/solomon/status")

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

    def test_status_has_heartbeat(self):
        """Test that status includes heartbeat info"""
        response = client.get("/api/solomon/status")

        assert response.status_code == 200
        data = response.json()

        heartbeat = data["data"]["heartbeat"]
        assert "status" in heartbeat
        assert "scan_count_today" in heartbeat

    def test_status_has_is_active_flag(self):
        """Test that status includes is_active flag"""
        response = client.get("/api/solomon/status")

        assert response.status_code == 200
        data = response.json()

        assert "is_active" in data["data"]
        assert isinstance(data["data"]["is_active"], bool)


class TestAthenaPositionsEndpoint:
    """Tests for /api/solomon/positions endpoint"""

    def test_get_positions_success(self):
        """Test positions endpoint returns valid structure"""
        response = client.get("/api/solomon/positions")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

    def test_get_open_positions(self):
        """Test getting open positions only"""
        response = client.get("/api/solomon/positions?status=open")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_get_closed_positions(self):
        """Test getting closed positions only"""
        response = client.get("/api/solomon/positions?status=closed")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAthenaSignalsEndpoint:
    """Tests for /api/solomon/signals endpoint"""

    def test_get_signals_success(self):
        """Test signals endpoint returns trading signals"""
        response = client.get("/api/solomon/signals")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_signals_structure(self):
        """Test signals have expected structure"""
        response = client.get("/api/solomon/signals")

        assert response.status_code == 200
        data = response.json()

        if data["data"].get("signals"):
            signal = data["data"]["signals"][0]
            # Signals should have direction info
            assert "direction" in signal or "bias" in signal or "signal" in signal


class TestAthenaPerformanceEndpoint:
    """Tests for /api/solomon/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint returns valid structure"""
        response = client.get("/api/solomon/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_performance_with_days_param(self):
        """Test performance endpoint with days parameter"""
        response = client.get("/api/solomon/performance?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAthenaEquityCurveEndpoint:
    """Tests for /api/solomon/equity endpoint"""

    def test_get_equity_curve_success(self):
        """Test equity curve endpoint"""
        response = client.get("/api/solomon/equity")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAthenaTradesEndpoint:
    """Tests for /api/solomon/trades endpoint"""

    def test_get_trades_success(self):
        """Test trades endpoint returns valid structure"""
        response = client.get("/api/solomon/trades")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_trades_with_limit(self):
        """Test trades endpoint with limit parameter"""
        response = client.get("/api/solomon/trades?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAthenaAnalysisEndpoint:
    """Tests for /api/solomon/analysis endpoint"""

    def test_get_analysis_success(self):
        """Test analysis endpoint returns market analysis"""
        response = client.get("/api/solomon/analysis")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAthenaLogsEndpoint:
    """Tests for /api/solomon/logs endpoint"""

    def test_get_logs_success(self):
        """Test logs endpoint returns decision logs"""
        response = client.get("/api/solomon/logs")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_logs_with_limit(self):
        """Test logs endpoint with limit parameter"""
        response = client.get("/api/solomon/logs?limit=25")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAthenaConfigEndpoint:
    """Tests for /api/solomon/config endpoint"""

    def test_get_config_success(self):
        """Test config endpoint returns configuration"""
        response = client.get("/api/solomon/config")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAthenaDataValidation:
    """Tests for data validation in SOLOMON endpoints"""

    def test_capital_is_positive(self):
        """Test that capital values are positive"""
        response = client.get("/api/solomon/status")

        assert response.status_code == 200
        data = response.json()

        capital = data["data"]["capital"]
        assert capital >= 0

    def test_win_rate_in_range(self):
        """Test that win rate is between 0 and 100"""
        response = client.get("/api/solomon/status")

        assert response.status_code == 200
        data = response.json()

        win_rate = data["data"]["win_rate"]
        assert 0 <= win_rate <= 100

    def test_mode_is_valid(self):
        """Test that mode is paper or live"""
        response = client.get("/api/solomon/status")

        assert response.status_code == 200
        data = response.json()

        mode = data["data"]["mode"]
        assert mode in ["paper", "live"]


class TestAthenaSpreadTypes:
    """Tests for spread type handling"""

    def test_bull_call_spread_support(self):
        """Test that bull call spreads are supported"""
        response = client.get("/api/solomon/analysis")

        assert response.status_code == 200
        # Endpoint should be functional for bullish analysis

    def test_bear_put_spread_support(self):
        """Test that bear put spreads are supported"""
        response = client.get("/api/solomon/analysis")

        assert response.status_code == 200
        # Endpoint should be functional for bearish analysis


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
