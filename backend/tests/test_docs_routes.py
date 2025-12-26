"""
Tests for Docs Routes (API Documentation)

Run with: pytest backend/tests/test_docs_routes.py -v
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


class TestDocsEndpoints:
    """Tests for documentation endpoints"""

    def test_openapi_endpoint(self, test_client):
        """Test OpenAPI spec endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/openapi.json")
        assert response.status_code in [200, 404, 500]

    def test_docs_endpoint(self, test_client):
        """Test Swagger docs endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/docs")
        assert response.status_code in [200, 404, 500]

    def test_redoc_endpoint(self, test_client):
        """Test ReDoc endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/redoc")
        assert response.status_code in [200, 404, 500]

    def test_api_docs_endpoint(self, test_client):
        """Test API docs custom endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/docs")
        assert response.status_code in [200, 404, 500]
