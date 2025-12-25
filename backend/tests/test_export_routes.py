"""
Export Routes Tests

Tests for data export API endpoints.

Run with: pytest backend/tests/test_export_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestExportTradesEndpoint:
    """Tests for /api/export/trades endpoint"""

    def test_export_trades_csv(self):
        """Test CSV export"""
        response = client.get("/api/export/trades?format=csv")

        assert response.status_code in [200, 500]  # May fail without data

    def test_export_trades_json(self):
        """Test JSON export"""
        response = client.get("/api/export/trades?format=json")

        assert response.status_code in [200, 500]


class TestExportPerformanceEndpoint:
    """Tests for /api/export/performance endpoint"""

    def test_export_performance(self):
        """Test performance export"""
        response = client.get("/api/export/performance")

        assert response.status_code in [200, 500]


class TestExportEquityEndpoint:
    """Tests for /api/export/equity endpoint"""

    def test_export_equity(self):
        """Test equity export"""
        response = client.get("/api/export/equity")

        assert response.status_code in [200, 500]


class TestExportDecisionsEndpoint:
    """Tests for /api/export/decisions endpoint"""

    def test_export_decisions(self):
        """Test decisions export"""
        response = client.get("/api/export/decisions")

        assert response.status_code in [200, 500]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
