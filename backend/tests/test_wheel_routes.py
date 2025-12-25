"""
Wheel Strategy Routes Tests

Tests for the Wheel strategy API endpoints including:
- Wheel phases
- Cycle management
- Performance tracking

Run with: pytest backend/tests/test_wheel_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestWheelStatusEndpoint:
    """Tests for /api/wheel/status endpoint"""

    def test_get_status_success(self):
        """Test that status endpoint returns valid data structure"""
        response = client.get("/api/wheel/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data


class TestWheelPhasesEndpoint:
    """Tests for /api/wheel/phases endpoint"""

    def test_get_phases_success(self):
        """Test phases endpoint returns valid structure"""
        response = client.get("/api/wheel/phases")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_phases_have_descriptions(self):
        """Test that phases include descriptions"""
        response = client.get("/api/wheel/phases")

        assert response.status_code == 200
        data = response.json()

        if data["data"].get("phases"):
            phase = data["data"]["phases"][0]
            assert "name" in phase or "phase" in phase


class TestWheelCyclesEndpoint:
    """Tests for /api/wheel/cycles endpoint"""

    def test_get_cycles_success(self):
        """Test cycles endpoint returns valid structure"""
        response = client.get("/api/wheel/cycles")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_cycles_with_limit(self):
        """Test cycles with limit parameter"""
        response = client.get("/api/wheel/cycles?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestWheelPositionsEndpoint:
    """Tests for /api/wheel/positions endpoint"""

    def test_get_positions_success(self):
        """Test positions endpoint returns valid structure"""
        response = client.get("/api/wheel/positions")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestWheelPerformanceEndpoint:
    """Tests for /api/wheel/performance endpoint"""

    def test_get_performance_success(self):
        """Test performance endpoint returns metrics"""
        response = client.get("/api/wheel/performance")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestWheelCandidatesEndpoint:
    """Tests for /api/wheel/candidates endpoint"""

    def test_get_candidates_success(self):
        """Test candidates endpoint returns wheel candidates"""
        response = client.get("/api/wheel/candidates")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestWheelAnalysisEndpoint:
    """Tests for /api/wheel/analysis endpoint"""

    def test_get_analysis_success(self):
        """Test analysis endpoint returns wheel analysis"""
        response = client.get("/api/wheel/analysis")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_analysis_with_symbol(self):
        """Test analysis with specific symbol"""
        response = client.get("/api/wheel/analysis?symbol=SPY")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestWheelEquityEndpoint:
    """Tests for /api/wheel/equity endpoint"""

    def test_get_equity_success(self):
        """Test equity curve endpoint"""
        response = client.get("/api/wheel/equity")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestWheelDataValidation:
    """Tests for data validation in Wheel endpoints"""

    def test_phase_is_valid(self):
        """Test that phase is a valid wheel phase"""
        response = client.get("/api/wheel/status")

        assert response.status_code == 200
        data = response.json()

        if "phase" in data.get("data", {}):
            phase = data["data"]["phase"]
            valid_phases = ["cash_secured_put", "assigned", "covered_call", "called_away", "none"]
            assert phase.lower() in [p.lower() for p in valid_phases] or phase is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
