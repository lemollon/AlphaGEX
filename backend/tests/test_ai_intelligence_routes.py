"""
AI Intelligence Routes Tests

Tests for AI-powered intelligence API endpoints.

Run with: pytest backend/tests/test_ai_intelligence_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestAIInsightsEndpoint:
    """Tests for /api/ai/insights endpoint"""

    def test_get_insights_success(self):
        """Test AI insights endpoint"""
        response = client.get("/api/ai/insights")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAIRecommendationsEndpoint:
    """Tests for /api/ai/recommendations endpoint"""

    def test_get_recommendations_success(self):
        """Test recommendations endpoint"""
        response = client.get("/api/ai/recommendations")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAICommentaryEndpoint:
    """Tests for /api/ai/commentary endpoint"""

    def test_get_commentary_success(self):
        """Test commentary endpoint"""
        response = client.get("/api/ai/commentary")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAIAnalysisEndpoint:
    """Tests for /api/ai/analysis endpoint"""

    def test_get_analysis_success(self):
        """Test analysis endpoint"""
        response = client.get("/api/ai/analysis")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAIExplainEndpoint:
    """Tests for /api/ai/explain endpoint"""

    def test_explain_success(self):
        """Test explain endpoint"""
        response = client.get("/api/ai/explain")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestAIChatEndpoint:
    """Tests for /api/ai/chat endpoint"""

    def test_chat_endpoint_exists(self):
        """Test chat endpoint exists"""
        response = client.get("/api/ai/chat")

        # Could be GET or POST only
        assert response.status_code in [200, 405, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
