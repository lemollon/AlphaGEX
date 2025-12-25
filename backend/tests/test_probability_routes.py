"""
Probability Routes Tests

Tests for probability calculation API endpoints including:
- Win probability
- Expected move
- Probability distributions

Run with: pytest backend/tests/test_probability_routes.py -v
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app

client = TestClient(app)


class TestProbabilityCalculateEndpoint:
    """Tests for /api/probability/calculate endpoint"""

    def test_calculate_success(self):
        """Test probability calculation endpoint"""
        response = client.get("/api/probability/calculate")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_calculate_with_params(self):
        """Test calculation with parameters"""
        response = client.get("/api/probability/calculate?symbol=SPY&strike=580")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestProbabilityExpectedMoveEndpoint:
    """Tests for /api/probability/expected-move endpoint"""

    def test_get_expected_move_success(self):
        """Test expected move endpoint"""
        response = client.get("/api/probability/expected-move")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True

    def test_expected_move_with_symbol(self):
        """Test expected move with symbol"""
        response = client.get("/api/probability/expected-move?symbol=SPY")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestProbabilityDistributionEndpoint:
    """Tests for /api/probability/distribution endpoint"""

    def test_get_distribution_success(self):
        """Test distribution endpoint"""
        response = client.get("/api/probability/distribution")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestProbabilityIronCondorEndpoint:
    """Tests for /api/probability/iron-condor endpoint"""

    def test_calculate_ic_probability(self):
        """Test iron condor probability calculation"""
        response = client.get("/api/probability/iron-condor")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestProbabilitySpreadEndpoint:
    """Tests for /api/probability/spread endpoint"""

    def test_calculate_spread_probability(self):
        """Test spread probability calculation"""
        response = client.get("/api/probability/spread")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True


class TestProbabilityDataValidation:
    """Tests for probability data validation"""

    def test_probability_in_range(self):
        """Test that probabilities are between 0 and 100"""
        response = client.get("/api/probability/calculate")

        assert response.status_code == 200
        data = response.json()

        if "probability" in data.get("data", {}):
            prob = data["data"]["probability"]
            assert 0 <= prob <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
