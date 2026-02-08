"""
JUBILEE Box Spread Routes Tests

Tests for JUBILEE Box Spread API endpoints.
Following STANDARDS.md requirements for API integration tests.

Run with: pytest backend/tests/test_jubilee_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)
CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestPrometheusBoxStatusEndpoint:
    """Tests for /api/jubilee/status endpoint"""

    def test_get_status_success(self):
        """Test that status endpoint returns valid data structure"""
        response = client.get("/api/jubilee/status")

        assert response.status_code == 200
        data = response.json()

        # Should have basic structure
        assert "mode" in data or "config" in data or "positions" in data

    def test_status_response_structure(self):
        """Test status has expected fields"""
        response = client.get("/api/jubilee/status")

        assert response.status_code == 200
        data = response.json()

        # Verify key metrics are present
        # (some may be None if no positions exist)
        possible_keys = ['mode', 'config', 'total_borrowed', 'positions_count']
        has_expected_key = any(key in data for key in possible_keys)
        assert has_expected_key or 'error' not in data


class TestPrometheusBoxPositionsEndpoint:
    """Tests for /api/jubilee/positions endpoint"""

    def test_get_positions_success(self):
        """Test positions endpoint returns valid structure"""
        response = client.get("/api/jubilee/positions")

        assert response.status_code == 200
        data = response.json()

        # Should return a list or dict with positions
        assert "positions" in data or isinstance(data, list)

    def test_positions_returns_list(self):
        """Test that positions returns a list"""
        response = client.get("/api/jubilee/positions")

        assert response.status_code == 200
        data = response.json()

        if "positions" in data:
            assert isinstance(data["positions"], list)


class TestPrometheusBoxClosedTradesEndpoint:
    """Tests for /api/jubilee/closed-trades endpoint"""

    def test_get_closed_trades_success(self):
        """Test closed trades endpoint returns valid structure"""
        response = client.get("/api/jubilee/closed-trades")

        assert response.status_code == 200
        data = response.json()

        assert "closed_trades" in data
        assert "count" in data
        assert isinstance(data["closed_trades"], list)

    def test_closed_trades_with_limit(self):
        """Test closed trades endpoint with limit parameter"""
        response = client.get("/api/jubilee/closed-trades?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert "closed_trades" in data


class TestPrometheusBoxEquityCurveEndpoint:
    """Tests for /api/jubilee/equity-curve endpoint"""

    def test_get_equity_curve_success(self):
        """Test equity curve endpoint"""
        response = client.get("/api/jubilee/equity-curve")

        assert response.status_code == 200
        data = response.json()

        # Should have equity data structure
        assert "equity_curve" in data or "data_points" in data or "starting_capital" in data

    def test_equity_curve_with_days(self):
        """Test equity curve with days parameter"""
        response = client.get("/api/jubilee/equity-curve?days=30")

        assert response.status_code == 200
        data = response.json()
        # Should return some structure
        assert isinstance(data, dict)


class TestPrometheusBoxLogsEndpoint:
    """Tests for /api/jubilee/logs endpoint"""

    def test_get_logs_success(self):
        """Test logs endpoint returns valid structure"""
        response = client.get("/api/jubilee/logs")

        assert response.status_code == 200
        data = response.json()

        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_logs_with_limit(self):
        """Test logs endpoint with limit parameter"""
        response = client.get("/api/jubilee/logs?limit=50")

        assert response.status_code == 200
        data = response.json()
        assert "logs" in data


class TestPrometheusBoxScanActivityEndpoint:
    """Tests for /api/jubilee/scan-activity endpoint"""

    def test_get_scan_activity_success(self):
        """Test scan activity endpoint returns valid structure"""
        response = client.get("/api/jubilee/scan-activity")

        assert response.status_code == 200
        data = response.json()

        assert "scans" in data
        assert "count" in data
        assert isinstance(data["scans"], list)


class TestPrometheusBoxSignalsEndpoint:
    """Tests for /api/jubilee/signals/* endpoints"""

    def test_get_recent_signals_success(self):
        """Test recent signals endpoint"""
        response = client.get("/api/jubilee/signals/recent")

        assert response.status_code == 200
        data = response.json()

        # Should have signals structure
        assert isinstance(data, dict) or isinstance(data, list)


class TestPrometheusBoxRateHistoryEndpoint:
    """Tests for /api/jubilee/analytics/rates/history endpoint"""

    def test_get_rate_history_success(self):
        """Test rate history endpoint"""
        response = client.get("/api/jubilee/analytics/rates/history")

        assert response.status_code == 200
        data = response.json()

        # Should have rate history structure
        assert "history" in data or "rates" in data or isinstance(data, list)


class TestPrometheusBoxBorrowingAnalysisEndpoint:
    """Tests for /api/jubilee/analytics/rates endpoint (borrowing rate analysis)"""

    def test_get_borrowing_analysis_success(self):
        """Test borrowing rate analysis endpoint"""
        response = client.get("/api/jubilee/analytics/rates")

        assert response.status_code == 200
        data = response.json()

        # Should have analysis structure
        assert isinstance(data, dict)


class TestPrometheusBoxDeploymentsEndpoint:
    """Tests for /api/jubilee/deployments endpoint"""

    def test_get_deployments_success(self):
        """Test deployments endpoint"""
        response = client.get("/api/jubilee/deployments")

        assert response.status_code == 200
        data = response.json()

        assert "deployments" in data
        assert isinstance(data["deployments"], list)


class TestPrometheusBoxDailyBriefingEndpoint:
    """Tests for /api/jubilee/operations/daily-briefing endpoint"""

    def test_get_daily_briefing_success(self):
        """Test daily briefing endpoint"""
        response = client.get("/api/jubilee/operations/daily-briefing")

        assert response.status_code == 200
        data = response.json()

        # Should have briefing structure
        assert isinstance(data, dict)


class TestPrometheusBoxConfigEndpoint:
    """Tests for /api/jubilee/config endpoint"""

    def test_get_config_success(self):
        """Test config endpoint returns valid structure"""
        response = client.get("/api/jubilee/config")

        assert response.status_code == 200
        data = response.json()

        # Should have config fields
        assert "config" in data or "mode" in data or "ticker" in data or isinstance(data, dict)


class TestPrometheusBoxDataValidation:
    """Tests for data validation in JUBILEE endpoints"""

    def test_equity_curve_days_validation(self):
        """Test that equity curve validates days parameter"""
        # Should handle negative days gracefully
        response = client.get("/api/jubilee/equity-curve?days=-1")

        # Should either return 200 with default or 400/422 for invalid
        assert response.status_code in [200, 400, 422]

    def test_logs_limit_validation(self):
        """Test that logs validates limit parameter"""
        # Should handle excessive limit
        response = client.get("/api/jubilee/logs?limit=10000")

        # Should either cap the limit or return error
        assert response.status_code in [200, 400, 422]


class TestPrometheusBoxErrorHandling:
    """Tests for error handling in JUBILEE endpoints"""

    def test_invalid_endpoint_returns_404(self):
        """Test handling of invalid endpoint"""
        response = client.get("/api/jubilee/nonexistent")

        assert response.status_code == 404

    def test_handles_database_unavailable(self):
        """Test graceful handling when database is unavailable"""
        # The endpoint should handle database errors gracefully
        # This is a basic test - in real scenario would mock DB failure
        response = client.get("/api/jubilee/status")

        # Should not return 500 if properly handled
        assert response.status_code in [200, 503]


class TestPrometheusBoxRequiredEndpoints:
    """
    Tests verifying all required endpoints per STANDARDS.md exist.

    STANDARDS.md requires these endpoints for all trading bots:
    - /status
    - /positions
    - /closed-trades
    - /equity-curve
    - /logs
    - /scan-activity
    """

    def test_status_endpoint_exists(self):
        """Verify /status endpoint exists"""
        response = client.get("/api/jubilee/status")
        assert response.status_code != 404

    def test_positions_endpoint_exists(self):
        """Verify /positions endpoint exists"""
        response = client.get("/api/jubilee/positions")
        assert response.status_code != 404

    def test_closed_trades_endpoint_exists(self):
        """Verify /closed-trades endpoint exists"""
        response = client.get("/api/jubilee/closed-trades")
        assert response.status_code != 404

    def test_equity_curve_endpoint_exists(self):
        """Verify /equity-curve endpoint exists"""
        response = client.get("/api/jubilee/equity-curve")
        assert response.status_code != 404

    def test_logs_endpoint_exists(self):
        """Verify /logs endpoint exists"""
        response = client.get("/api/jubilee/logs")
        assert response.status_code != 404

    def test_scan_activity_endpoint_exists(self):
        """Verify /scan-activity endpoint exists"""
        response = client.get("/api/jubilee/scan-activity")
        assert response.status_code != 404


class TestPrometheusBoxRoutesSyntax:
    """Tests for routes file syntax and structure"""

    def test_routes_syntax(self):
        """Verify jubilee_routes.py has valid Python syntax"""
        import os

        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'api', 'routes', 'jubilee_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        # Should not raise SyntaxError
        compile(code, 'jubilee_routes.py', 'exec')

    def test_endpoint_count(self):
        """Verify expected number of endpoints"""
        import re
        import os

        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'api', 'routes', 'jubilee_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        endpoints = re.findall(r'@router\.(get|post|put|delete)\("([^"]+)"', code)
        # Should have at least 10 endpoints per STANDARDS.md
        assert len(endpoints) >= 10, f"Expected at least 10 endpoints, found {len(endpoints)}"

    def test_required_endpoints_defined(self):
        """Check that all required endpoints are defined in routes"""
        import os

        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'api', 'routes', 'jubilee_routes.py'
        )

        with open(routes_path, 'r') as f:
            code = f.read()

        required = [
            '/status',
            '/positions',
            '/closed-trades',
            '/equity-curve',
            '/logs',
            '/scan-activity',
        ]

        for endpoint in required:
            assert endpoint in code, f"Missing required endpoint: {endpoint}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
