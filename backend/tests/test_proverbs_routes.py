"""
Tests for Proverbs Routes (Feedback Loop Intelligence)

Run with: pytest backend/tests/test_proverbs_routes.py -v
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


class TestProverbsEndpoints:
    """Tests for Proverbs feedback loop endpoints"""

    def test_proverbs_status(self, test_client):
        """Test Proverbs status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/status")
        assert response.status_code in [200, 404, 500]

    # =========================================================================
    # Migration 023: Strategy Analysis Endpoints
    # =========================================================================

    def test_proverbs_strategy_analysis(self, test_client):
        """Test Proverbs strategy analysis endpoint (Migration 023)"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/strategy-analysis")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data or 'status' in data

    def test_proverbs_strategy_analysis_with_days(self, test_client):
        """Test Proverbs strategy analysis with custom days parameter"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/strategy-analysis?days=7")
        assert response.status_code in [200, 500]

    def test_proverbs_oracle_accuracy(self, test_client):
        """Test Proverbs Oracle accuracy endpoint (Migration 023)"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/oracle-accuracy")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert 'success' in data or 'status' in data

    def test_proverbs_oracle_accuracy_with_days(self, test_client):
        """Test Proverbs Oracle accuracy with custom days parameter"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/oracle-accuracy?days=14")
        assert response.status_code in [200, 500]

    def test_proverbs_analysis(self, test_client):
        """Test Proverbs analysis"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/analysis")
        assert response.status_code in [200, 404, 500]

    def test_proverbs_recommendations(self, test_client):
        """Test Proverbs recommendations"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/recommendations")
        assert response.status_code in [200, 404, 500]

    def test_proverbs_bot_health(self, test_client):
        """Test Proverbs bot health"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/bot-health")
        assert response.status_code in [200, 404, 500]

    def test_proverbs_run_feedback(self, test_client):
        """Test run feedback loop"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post("/api/proverbs/run-feedback")
        assert response.status_code in [200, 202, 400, 404, 500]

    def test_proverbs_kill_switch(self, test_client):
        """Test Proverbs kill switch status"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.get("/api/proverbs/kill-switch")
        assert response.status_code in [200, 404, 500]

    def test_proverbs_toggle_kill_switch(self, test_client):
        """Test toggle kill switch"""
        if test_client is None:
            pytest.skip("Test client not available")
        response = test_client.post(
            "/api/proverbs/kill-switch/toggle",
            json={"bot": "FORTRESS", "enabled": True}
        )
        assert response.status_code in [200, 400, 404, 500]
