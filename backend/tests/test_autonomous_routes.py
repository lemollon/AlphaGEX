"""
Autonomous Bot Routes Tests

Tests for autonomous trading bot API endpoints including:
- Bot status and control
- Decision logs
- Performance tracking

Run with: pytest backend/tests/test_autonomous_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestAutonomousStatusEndpoint:
    """Tests for /api/autonomous/status endpoint"""

    def test_get_status_success(self):
        """Test autonomous status endpoint"""
        response = client.get("/api/autonomous/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAutonomousBotsEndpoint:
    """Tests for /api/autonomous/bots endpoint"""

    def test_get_bots_success(self):
        """Test bots list endpoint"""
        response = client.get("/api/autonomous/bots")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAutonomousDecisionsEndpoint:
    """Tests for /api/autonomous/decisions endpoint"""

    def test_get_decisions_success(self):
        """Test decisions endpoint"""
        response = client.get("/api/autonomous/decisions")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_decisions_with_limit(self):
        """Test decisions with limit"""
        response = client.get("/api/autonomous/decisions?limit=20")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestAutonomousPerformanceEndpoint:
    """Tests for /api/autonomous/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint"""
        response = client.get("/api/autonomous/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAutonomousLogsEndpoint:
    """Tests for /api/autonomous/logs endpoint"""

    def test_get_logs_success(self):
        """Test logs endpoint"""
        response = client.get("/api/autonomous/logs")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAutonomousHeartbeatEndpoint:
    """Tests for /api/autonomous/heartbeat endpoint"""

    def test_get_heartbeat_success(self):
        """Test heartbeat endpoint"""
        response = client.get("/api/autonomous/heartbeat")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
