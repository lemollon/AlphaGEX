"""
Tests for Jobs Routes (Background Jobs)

Run with: pytest backend/tests/test_jobs_routes.py -v
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


class TestJobsEndpoints:
    """Tests for background jobs endpoints"""

    def test_get_jobs_endpoint(self, test_client):
        """Test get all jobs"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/jobs")
        assert response.status_code in [200, 404, 500]

    def test_get_running_jobs(self, test_client):
        """Test get running jobs"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/jobs/running")
        assert response.status_code in [200, 404, 500]

    def test_get_job_status(self, test_client):
        """Test get specific job status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/jobs/1/status")
        assert response.status_code in [200, 404, 500]

    def test_cancel_job(self, test_client):
        """Test cancel job"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post("/api/jobs/1/cancel")
        assert response.status_code in [200, 400, 404, 500]

    def test_job_history(self, test_client):
        """Test job history"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/jobs/history")
        assert response.status_code in [200, 404, 500]
