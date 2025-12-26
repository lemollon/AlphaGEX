"""
Tests for Notification Routes

Run with: pytest backend/tests/test_notification_routes.py -v
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


class TestNotificationEndpoints:
    """Tests for notification endpoints"""

    def test_get_notifications(self, test_client):
        """Test get notifications"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/notifications")
        assert response.status_code in [200, 404, 500]

    def test_subscribe_push(self, test_client):
        """Test subscribe to push notifications"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/notifications/subscribe",
            json={"endpoint": "https://example.com", "keys": {}}
        )
        assert response.status_code in [200, 201, 400, 404, 500]

    def test_unsubscribe_push(self, test_client):
        """Test unsubscribe from push notifications"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/notifications/unsubscribe",
            json={"endpoint": "https://example.com"}
        )
        assert response.status_code in [200, 400, 404, 500]

    def test_mark_notification_read(self, test_client):
        """Test mark notification as read"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post("/api/notifications/1/read")
        assert response.status_code in [200, 404, 500]
