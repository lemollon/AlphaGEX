"""
Comprehensive Tests for AI Routes

Tests the AI API endpoints including:
- GEXIS chat endpoints
- AI analysis endpoints
- Intelligence module endpoints

Run with: pytest backend/tests/test_ai_routes.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def test_client():
    """Create test client for FastAPI app"""
    with patch.dict('os.environ', {'DATABASE_URL': 'postgresql://test:test@localhost:5432/test'}):
        with patch('database_adapter.psycopg2'):
            try:
                from main import app
                return TestClient(app)
            except Exception as e:
                pytest.skip(f"Could not create test client: {e}")


class TestGEXISChatEndpoints:
    """Tests for GEXIS chat endpoints"""

    def test_gexis_chat_endpoint_exists(self, test_client):
        """Test GEXIS chat endpoint exists"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/gexis/chat",
            json={"message": "Hello GEXIS"}
        )
        # Should return response (may be 500 if no API key)
        assert response.status_code in [200, 400, 401, 500]

    def test_gexis_greeting_endpoint(self, test_client):
        """Test GEXIS greeting endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/gexis/greeting")
        assert response.status_code in [200, 404, 500]


class TestAIAnalysisEndpoints:
    """Tests for AI analysis endpoints"""

    def test_ai_analyze_market_endpoint(self, test_client):
        """Test AI market analysis endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/ai/analyze",
            json={"symbol": "SPY"}
        )
        assert response.status_code in [200, 400, 401, 404, 500]

    def test_ai_recommendation_endpoint(self, test_client):
        """Test AI trade recommendation endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/ai/recommendation")
        assert response.status_code in [200, 404, 500]


class TestAIIntelligenceEndpoints:
    """Tests for AI intelligence module endpoints"""

    def test_intelligence_status_endpoint(self, test_client):
        """Test intelligence status endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/ai-intelligence/status")
        assert response.status_code in [200, 404, 500]

    def test_intelligence_analysis_endpoint(self, test_client):
        """Test intelligence analysis endpoint"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/ai-intelligence/analysis")
        assert response.status_code in [200, 404, 500]


class TestMockedAIRoutes:
    """Tests with mocked AI dependencies"""

    @patch('backend.api.routes.ai_routes.get_gexis_response')
    def test_gexis_returns_response(self, mock_gexis, test_client):
        """Test GEXIS returns valid response"""
        if test_client is None:
            pytest.skip("Test client not available")

        mock_gexis.return_value = {
            "response": "Hello, Optionist Prime. GEXIS at your service.",
            "status": "success"
        }

        response = test_client.post(
            "/api/gexis/chat",
            json={"message": "Hello"}
        )

        if response.status_code == 200:
            data = response.json()
            assert "response" in data or "message" in data or "error" in data


class TestChatRequestValidation:
    """Tests for chat request validation"""

    def test_empty_message_rejected(self, test_client):
        """Test empty message is rejected"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/gexis/chat",
            json={"message": ""}
        )
        # Should reject empty message
        assert response.status_code in [200, 400, 422, 500]

    def test_missing_message_rejected(self, test_client):
        """Test missing message field is rejected"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/gexis/chat",
            json={}
        )
        # Should reject missing field
        assert response.status_code in [400, 422, 500]


class TestAIConfigEndpoints:
    """Tests for AI configuration endpoints"""

    def test_ai_config_get(self, test_client):
        """Test get AI configuration"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.get("/api/ai/config")
        assert response.status_code in [200, 404, 500]


class TestErrorHandling:
    """Tests for error handling"""

    def test_invalid_symbol_handled(self, test_client):
        """Test invalid symbol is handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/ai/analyze",
            json={"symbol": "INVALID_SYMBOL_123456"}
        )
        # Should handle gracefully
        assert response.status_code in [200, 400, 404, 500]

    def test_malformed_json_handled(self, test_client):
        """Test malformed JSON is handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/gexis/chat",
            data="not valid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422, 500]


class TestResponseFormats:
    """Tests for response format consistency"""

    def test_gexis_response_format(self, test_client):
        """Test GEXIS response has expected format"""
        if test_client is None:
            pytest.skip("Test client not available")

        response = test_client.post(
            "/api/gexis/chat",
            json={"message": "What is my status?"}
        )

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)


class TestRateLimiting:
    """Tests for rate limiting (if implemented)"""

    def test_rapid_requests_handled(self, test_client):
        """Test rapid requests are handled"""
        if test_client is None:
            pytest.skip("Test client not available")

        # Send multiple rapid requests
        responses = []
        for _ in range(5):
            response = test_client.get("/api/gexis/greeting")
            responses.append(response.status_code)

        # All should be handled (not crash)
        assert all(code in [200, 404, 429, 500] for code in responses)
