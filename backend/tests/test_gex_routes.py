"""
GEX (Gamma Exposure) Routes Tests

Tests for GEX-related API endpoints including:
- Current GEX
- GEX levels
- GEX history

Run with: pytest backend/tests/test_gex_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestGexCurrentEndpoint:
    """Tests for /api/gex/current endpoint"""

    def test_get_current_success(self):
        """Test current GEX endpoint"""
        response = client.get("/api/gex/current")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_current_with_symbol(self):
        """Test current with symbol"""
        response = client.get("/api/gex/current?symbol=SPY")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestGexLevelsEndpoint:
    """Tests for /api/gex/levels endpoint"""

    def test_get_levels_success(self):
        """Test GEX levels endpoint"""
        response = client.get("/api/gex/levels")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGexHistoryEndpoint:
    """Tests for /api/gex/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/gex/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGexProfileEndpoint:
    """Tests for /api/gex/profile endpoint"""

    def test_get_profile_success(self):
        """Test profile endpoint"""
        response = client.get("/api/gex/profile")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGexWallsEndpoint:
    """Tests for /api/gex/walls endpoint"""

    def test_get_walls_success(self):
        """Test walls endpoint"""
        response = client.get("/api/gex/walls")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGexFlipEndpoint:
    """Tests for /api/gex/flip endpoint"""

    def test_get_flip_success(self):
        """Test gamma flip endpoint"""
        response = client.get("/api/gex/flip")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
