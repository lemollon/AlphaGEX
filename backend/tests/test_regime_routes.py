"""
Regime Routes Tests

Tests for market regime API endpoints.

Run with: pytest backend/tests/test_regime_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestRegimeCurrentEndpoint:
    """Tests for /api/regime/current endpoint"""

    def test_get_current_success(self):
        """Test current regime endpoint"""
        response = client.get("/api/regime/current")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestRegimeHistoryEndpoint:
    """Tests for /api/regime/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/regime/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestRegimeClassificationEndpoint:
    """Tests for /api/regime/classification endpoint"""

    def test_get_classification_success(self):
        """Test classification endpoint"""
        response = client.get("/api/regime/classification")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestRegimeSignalEndpoint:
    """Tests for /api/regime/signal endpoint"""

    def test_get_signal_success(self):
        """Test signal endpoint"""
        response = client.get("/api/regime/signal")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
