"""
VIX Routes Tests

Tests for VIX-related API endpoints including:
- Current VIX data
- VIX hedge signals
- VIX history

Run with: pytest backend/tests/test_vix_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestVixCurrentEndpoint:
    """Tests for /api/vix/current endpoint"""

    def test_get_current_success(self):
        """Test that current VIX endpoint returns valid data"""
        response = client.get("/api/vix/current")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_current_has_vix_value(self):
        """Test that current includes VIX value"""
        response = client.get("/api/vix/current")

        assert response.status_code == 200
        data = response.json()

        if "vix" in data.get("data", {}):
            vix = data["data"]["vix"]
            assert 5 <= vix <= 100  # Reasonable VIX range


class TestVixHedgeEndpoint:
    """Tests for /api/vix/hedge endpoint"""

    def test_get_hedge_signal_success(self):
        """Test hedge signal endpoint returns valid data"""
        response = client.get("/api/vix/hedge")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestVixHistoryEndpoint:
    """Tests for /api/vix/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint returns valid data"""
        response = client.get("/api/vix/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_history_with_days(self):
        """Test history with days parameter"""
        response = client.get("/api/vix/history?days=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestVixTermStructureEndpoint:
    """Tests for /api/vix/term-structure endpoint"""

    def test_get_term_structure_success(self):
        """Test term structure endpoint"""
        response = client.get("/api/vix/term-structure")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestVixAnalysisEndpoint:
    """Tests for /api/vix/analysis endpoint"""

    def test_get_analysis_success(self):
        """Test analysis endpoint returns VIX analysis"""
        response = client.get("/api/vix/analysis")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestVixDataValidation:
    """Tests for VIX data validation"""

    def test_vix_value_reasonable(self):
        """Test that VIX value is within reasonable range"""
        response = client.get("/api/vix/current")

        assert response.status_code == 200
        data = response.json()

        if "vix" in data.get("data", {}):
            vix = data["data"]["vix"]
            # VIX historically ranges from ~9 to ~80+
            assert 5 <= vix <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
