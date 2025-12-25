"""
Psychology Routes Tests

Tests for psychology/emotional trading API endpoints including:
- Trap detection
- Emotional assessment
- Trading psychology recommendations

Run with: pytest backend/tests/test_psychology_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestPsychologyStatusEndpoint:
    """Tests for /api/psychology/status endpoint"""

    def test_get_status_success(self):
        """Test psychology status endpoint"""
        response = client.get("/api/psychology/status")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPsychologyTrapsEndpoint:
    """Tests for /api/psychology/traps endpoint"""

    def test_get_traps_success(self):
        """Test traps detection endpoint"""
        response = client.get("/api/psychology/traps")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPsychologyAssessmentEndpoint:
    """Tests for /api/psychology/assessment endpoint"""

    def test_get_assessment_success(self):
        """Test assessment endpoint"""
        response = client.get("/api/psychology/assessment")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPsychologyNotificationsEndpoint:
    """Tests for /api/psychology/notifications endpoint"""

    def test_get_notifications_success(self):
        """Test notifications endpoint"""
        response = client.get("/api/psychology/notifications")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_notifications_with_limit(self):
        """Test notifications with limit"""
        response = client.get("/api/psychology/notifications?limit=10")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestPsychologyHistoryEndpoint:
    """Tests for /api/psychology/history endpoint"""

    def test_get_history_success(self):
        """Test history endpoint"""
        response = client.get("/api/psychology/history")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPsychologyRecommendationsEndpoint:
    """Tests for /api/psychology/recommendations endpoint"""

    def test_get_recommendations_success(self):
        """Test recommendations endpoint"""
        response = client.get("/api/psychology/recommendations")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestPsychologyDataValidation:
    """Tests for psychology data validation"""

    def test_score_in_range(self):
        """Test that psychology score is in valid range"""
        response = client.get("/api/psychology/assessment")

        assert response.status_code == 200
        data = response.json()

        if "score" in data.get("data", {}):
            score = data["data"]["score"]
            assert 0 <= score <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
