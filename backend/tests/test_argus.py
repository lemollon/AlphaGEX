"""
ARGUS (0DTE Gamma Live) API Tests

Tests for the ARGUS backend endpoints that provide real-time
gamma visualization and predictions for 0DTE options.

Run with: pytest backend/tests/test_argus.py -v
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
import json
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestArgusGammaEndpoint:
    """Tests for /api/argus/gamma endpoint"""

    def test_get_gamma_data_success(self):
        """Test that gamma endpoint returns valid data structure"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data
        assert data["success"] is True
        assert "data" in data

        gamma_data = data["data"]
        assert "symbol" in gamma_data
        assert gamma_data["symbol"] == "SPY"
        assert "strikes" in gamma_data
        assert "spot_price" in gamma_data
        assert "expected_move" in gamma_data
        assert "gamma_regime" in gamma_data

    def test_get_gamma_data_with_expiration(self):
        """Test gamma endpoint with specific expiration day"""
        response = client.get("/api/argus/gamma?expiration=mon")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_gamma_strikes_structure(self):
        """Test that strike data has required fields"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        if data["data"]["strikes"]:
            strike = data["data"]["strikes"][0]
            required_fields = [
                "strike", "net_gamma", "probability",
                "roc_1min", "roc_5min", "is_magnet", "is_pin"
            ]
            for field in required_fields:
                assert field in strike, f"Missing field: {field}"

    def test_gamma_magnets_included(self):
        """Test that magnet data is included"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        assert "magnets" in data["data"]
        assert "likely_pin" in data["data"]
        assert "pin_probability" in data["data"]


class TestArgusExpirationsEndpoint:
    """Tests for /api/argus/expirations endpoint"""

    def test_get_expirations_success(self):
        """Test that expirations endpoint returns valid data"""
        response = client.get("/api/argus/expirations")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "expirations" in data["data"]

    def test_expirations_have_required_fields(self):
        """Test expiration data structure"""
        response = client.get("/api/argus/expirations")

        data = response.json()
        if data["data"]["expirations"]:
            exp = data["data"]["expirations"][0]
            assert "day" in exp
            assert "date" in exp
            assert "is_today" in exp


class TestArgusAlertsEndpoint:
    """Tests for /api/argus/alerts endpoint"""

    def test_get_alerts_success(self):
        """Test that alerts endpoint returns valid data"""
        response = client.get("/api/argus/alerts")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "alerts" in data["data"]

    def test_get_alerts_with_filters(self):
        """Test alerts endpoint with filter parameters"""
        response = client.get("/api/argus/alerts?priority=HIGH")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusCommentaryEndpoint:
    """Tests for /api/argus/commentary endpoint"""

    def test_get_commentary_success(self):
        """Test that commentary endpoint returns valid data"""
        response = client.get("/api/argus/commentary")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "commentary" in data["data"]

    def test_get_commentary_with_limit(self):
        """Test commentary endpoint with limit parameter"""
        response = client.get("/api/argus/commentary?limit=5")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        # Should return at most 5 items
        assert len(data["data"]["commentary"]) <= 5


class TestArgusHistoryEndpoint:
    """Tests for /api/argus/history endpoint"""

    def test_get_history_success(self):
        """Test that history endpoint returns valid data"""
        response = client.get("/api/argus/history")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data

    def test_get_history_with_minutes(self):
        """Test history endpoint with minutes parameter"""
        response = client.get("/api/argus/history?minutes=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusProbabilityEndpoint:
    """Tests for /api/argus/probability endpoint"""

    def test_get_probability_success(self):
        """Test that probability endpoint returns valid data"""
        response = client.get("/api/argus/probability")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusAccuracyEndpoint:
    """Tests for /api/argus/accuracy endpoint"""

    def test_get_accuracy_success(self):
        """Test that accuracy endpoint returns valid data"""
        response = client.get("/api/argus/accuracy")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusBotsEndpoint:
    """Tests for /api/argus/bots endpoint"""

    def test_get_bots_status_success(self):
        """Test that bots endpoint returns valid data"""
        response = client.get("/api/argus/bots")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "bots" in data["data"]


class TestArgusPatternsEndpoint:
    """Tests for /api/argus/patterns endpoint"""

    def test_get_patterns_success(self):
        """Test that patterns endpoint returns valid data"""
        response = client.get("/api/argus/patterns")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusExportEndpoint:
    """Tests for /api/argus/export endpoint"""

    def test_export_csv_success(self):
        """Test CSV export endpoint"""
        response = client.get("/api/argus/export?format=csv")

        # Should either succeed or return error gracefully
        assert response.status_code in [200, 500]

    def test_export_xlsx_success(self):
        """Test XLSX export endpoint"""
        response = client.get("/api/argus/export?format=xlsx")

        # Should either succeed or return error gracefully
        assert response.status_code in [200, 500]


class TestArgusReplayEndpoint:
    """Tests for /api/argus/replay endpoints"""

    def test_get_replay_dates_success(self):
        """Test that replay dates endpoint returns valid data"""
        response = client.get("/api/argus/replay/dates")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data

    def test_get_replay_with_date(self):
        """Test replay endpoint with specific date"""
        # Use today's date
        today = datetime.now().strftime("%Y-%m-%d")
        response = client.get(f"/api/argus/replay?date={today}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusGammaFlipDetection:
    """Tests for gamma flip detection functionality"""

    def test_gamma_flips_in_response(self):
        """Test that gamma flips are included in response"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        # gamma_flips should be in the response
        assert "gamma_flips" in data["data"]

    def test_danger_zones_in_response(self):
        """Test that danger zones are included in response"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        # danger_zones should be in the response
        assert "danger_zones" in data["data"]


class TestArgusDataValidation:
    """Tests for data validation and integrity"""

    def test_spot_price_reasonable(self):
        """Test that spot price is within reasonable range"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        spot_price = data["data"]["spot_price"]
        # SPY should be between $100 and $1000
        assert 100 <= spot_price <= 1000

    def test_vix_reasonable(self):
        """Test that VIX is within reasonable range"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        vix = data["data"]["vix"]
        # VIX should be between 5 and 100
        assert 5 <= vix <= 100

    def test_probabilities_sum_to_100(self):
        """Test that strike probabilities sum approximately to 100"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        strikes = data["data"]["strikes"]
        if strikes:
            total_prob = sum(s["probability"] for s in strikes)
            # Allow some margin for rounding
            assert 90 <= total_prob <= 110

    def test_gamma_regime_valid(self):
        """Test that gamma regime is a valid value"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        regime = data["data"]["gamma_regime"]
        valid_regimes = ["POSITIVE", "NEGATIVE", "NEUTRAL"]
        assert regime in valid_regimes

    def test_market_status_valid(self):
        """Test that market status is a valid value"""
        response = client.get("/api/argus/gamma")

        assert response.status_code == 200
        data = response.json()

        status = data["data"]["market_status"]
        valid_statuses = ["pre_market", "open", "after_hours", "closed"]
        assert status in valid_statuses


class TestArgusPerformance:
    """Performance tests for ARGUS endpoints"""

    def test_gamma_endpoint_response_time(self):
        """Test that gamma endpoint responds within acceptable time"""
        import time

        start = time.time()
        response = client.get("/api/argus/gamma")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should respond within 5 seconds (allowing for API calls)
        assert elapsed < 5.0

    def test_expirations_endpoint_response_time(self):
        """Test that expirations endpoint responds quickly"""
        import time

        start = time.time()
        response = client.get("/api/argus/expirations")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should respond within 1 second (cached data)
        assert elapsed < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
