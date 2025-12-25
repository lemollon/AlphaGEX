"""
Scanner Routes Tests

Tests for scanner API endpoints.

Run with: pytest backend/tests/test_scanner_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestScannerResultsEndpoint:
    """Tests for /api/scanner/results endpoint"""

    def test_get_results_success(self):
        """Test results endpoint"""
        response = client.get("/api/scanner/results")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestScannerActivityEndpoint:
    """Tests for /api/scanner/activity endpoint"""

    def test_get_activity_success(self):
        """Test activity endpoint"""
        response = client.get("/api/scanner/activity")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestScannerCandidatesEndpoint:
    """Tests for /api/scanner/candidates endpoint"""

    def test_get_candidates_success(self):
        """Test candidates endpoint"""
        response = client.get("/api/scanner/candidates")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
