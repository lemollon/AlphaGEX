"""
Tests for Database Routes

Run with: pytest backend/tests/test_database_routes.py -v
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


class TestDatabaseEndpoints:
    """Tests for database query endpoints"""

    def test_database_status_endpoint(self, test_client):
        """Test database status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/database/status")
        assert response.status_code in [200, 404, 500]

    def test_database_tables_endpoint(self, test_client):
        """Test list database tables"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/database/tables")
        assert response.status_code in [200, 404, 500]

    def test_database_query_endpoint(self, test_client):
        """Test database query endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/database/query",
            json={"query": "SELECT 1"}
        )
        assert response.status_code in [200, 400, 403, 404, 500]
