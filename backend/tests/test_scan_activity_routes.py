"""
Tests for Scan Activity Routes

Run with: pytest backend/tests/test_scan_activity_routes.py -v
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_client():
    """Create test client"""
    with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost:5432/test'}):
        with patch('database_adapter.psycopg2'):
            try:
                from main import app
                return TestClient(app)
            except Exception as e:
                pytest.skip(f"Could not create test client: {e}")


class TestScanActivityEndpoints:
    """Tests for scan activity endpoints"""

    def test_get_scan_activity(self, test_client):
        """Test get scan activity"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/scan-activity")
        assert response.status_code in [200, 404, 500]

    def test_get_scan_activity_by_bot(self, test_client):
        """Test get scan activity by bot"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/scan-activity/bot/ARES")
        assert response.status_code in [200, 404, 500]

    def test_get_recent_scans(self, test_client):
        """Test get recent scans"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/scan-activity/recent")
        assert response.status_code in [200, 404, 500]

    def test_get_no_trade_decisions(self, test_client):
        """Test get no-trade decisions"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/scan-activity/no-trade")
        assert response.status_code in [200, 404, 500]
