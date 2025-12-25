"""
Daily Manna Routes Tests

Tests for Daily Manna insight API endpoints.

Run with: pytest backend/tests/test_daily_manna_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestDailyMannaCurrentEndpoint:
    """Tests for /api/daily-manna/current endpoint"""

    def test_get_current_success(self):
        """Test current daily manna endpoint"""
        response = client.get("/api/daily-manna/current")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDailyMannaPlanEndpoint:
    """Tests for /api/daily-manna/plan endpoint"""

    def test_get_plan_success(self):
        """Test daily plan endpoint"""
        response = client.get("/api/daily-manna/plan")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDailyMannaInsightsEndpoint:
    """Tests for /api/daily-manna/insights endpoint"""

    def test_get_insights_success(self):
        """Test insights endpoint"""
        response = client.get("/api/daily-manna/insights")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDailyMannaHistoryEndpoint:
    """Tests for /api/daily-manna/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/daily-manna/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_history_with_days(self):
        """Test history with days param"""
        response = client.get("/api/daily-manna/history?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
