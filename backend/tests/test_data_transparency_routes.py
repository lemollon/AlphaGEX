"""
Data Transparency Routes Tests

Tests for data transparency API endpoints.

Run with: pytest backend/tests/test_data_transparency_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestDataTransparencyStatusEndpoint:
    """Tests for /api/data-transparency/status endpoint"""

    def test_get_status_success(self):
        """Test status endpoint"""
        response = client.get("/api/data-transparency/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDataTransparencySourcesEndpoint:
    """Tests for /api/data-transparency/sources endpoint"""

    def test_get_sources_success(self):
        """Test sources endpoint"""
        response = client.get("/api/data-transparency/sources")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDataTransparencyQualityEndpoint:
    """Tests for /api/data-transparency/quality endpoint"""

    def test_get_quality_success(self):
        """Test quality endpoint"""
        response = client.get("/api/data-transparency/quality")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestDataTransparencyFreshnessEndpoint:
    """Tests for /api/data-transparency/freshness endpoint"""

    def test_get_freshness_success(self):
        """Test freshness endpoint"""
        response = client.get("/api/data-transparency/freshness")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
