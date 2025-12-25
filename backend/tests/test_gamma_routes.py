"""
Gamma Routes Tests

Tests for gamma-related API endpoints including:
- Gamma exposure data
- Gamma levels
- Gamma expiration analysis

Run with: pytest backend/tests/test_gamma_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestGammaDataEndpoint:
    """Tests for /api/gamma/data endpoint"""

    def test_get_data_success(self):
        """Test gamma data endpoint"""
        response = client.get("/api/gamma/data")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGammaLevelsEndpoint:
    """Tests for /api/gamma/levels endpoint"""

    def test_get_levels_success(self):
        """Test gamma levels endpoint"""
        response = client.get("/api/gamma/levels")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_levels_with_symbol(self):
        """Test levels with symbol"""
        response = client.get("/api/gamma/levels?symbol=SPY")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestGammaExpirationEndpoint:
    """Tests for /api/gamma/expiration endpoint"""

    def test_get_expiration_success(self):
        """Test expiration endpoint"""
        response = client.get("/api/gamma/expiration")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGammaHistoryEndpoint:
    """Tests for /api/gamma/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/gamma/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_history_with_days(self):
        """Test history with days"""
        response = client.get("/api/gamma/history?days=7")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestGammaIntelEndpoint:
    """Tests for /api/gamma/intel endpoint"""

    def test_get_intel_success(self):
        """Test gamma intel endpoint"""
        response = client.get("/api/gamma/intel")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestGammaCorrelationEndpoint:
    """Tests for /api/gamma/correlation endpoint"""

    def test_get_correlation_success(self):
        """Test correlation endpoint"""
        response = client.get("/api/gamma/correlation")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
