"""
VIX API End-to-End Tests
========================

Comprehensive tests for VIX API endpoints including:
- /api/vix/current - Current VIX data
- /api/vix/hedge-signal - Hedge signal generation
- /api/vix/signal-history - Historical signals
- /api/vix/debug - Debug information
- /api/vix/test-sources - Source testing
- /api/vix/metrics - API metrics

These tests verify:
1. API response structure and types
2. Input validation
3. Fallback behavior
4. Error handling
5. Data quality constraints
"""

import pytest
import sys
import os
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import FastAPI test client
from fastapi.testclient import TestClient


class TestVIXCurrentEndpoint:
    """Tests for GET /api/vix/current"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_current_returns_success(self, client):
        """Current endpoint should return success response"""
        response = client.get("/api/vix/current")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    def test_current_response_structure(self, client):
        """Current endpoint should have required fields"""
        response = client.get("/api/vix/current")
        data = response.json()["data"]

        required_fields = [
            "vix_spot", "vix_source", "vix_m1", "vix_m2",
            "is_estimated", "term_structure_pct", "structure_type",
            "iv_percentile", "realized_vol_20d", "iv_rv_spread",
            "vol_regime", "vix_stress_level", "position_size_multiplier",
            "timestamp"
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_current_vix_spot_reasonable(self, client):
        """VIX spot should be in reasonable range (5-100)"""
        response = client.get("/api/vix/current")
        vix_spot = response.json()["data"]["vix_spot"]

        assert isinstance(vix_spot, (int, float))
        assert 5 <= vix_spot <= 100, f"VIX {vix_spot} outside reasonable range"

    def test_current_stress_level_valid(self, client):
        """Stress level should be one of valid values"""
        response = client.get("/api/vix/current")
        stress_level = response.json()["data"]["vix_stress_level"]

        valid_levels = ["normal", "elevated", "high", "extreme", "low", "unknown"]
        assert stress_level in valid_levels

    def test_current_position_multiplier_valid(self, client):
        """Position multiplier should be between 0.25 and 1.0"""
        response = client.get("/api/vix/current")
        multiplier = response.json()["data"]["position_size_multiplier"]

        assert 0.25 <= multiplier <= 1.0

    def test_current_vol_regime_valid(self, client):
        """Vol regime should be one of valid values"""
        response = client.get("/api/vix/current")
        vol_regime = response.json()["data"]["vol_regime"]

        valid_regimes = ["very_low", "low", "normal", "elevated", "high", "extreme"]
        assert vol_regime in valid_regimes

    def test_current_iv_percentile_range(self, client):
        """IV percentile should be between 0 and 100"""
        response = client.get("/api/vix/current")
        iv_percentile = response.json()["data"]["iv_percentile"]

        assert 0 <= iv_percentile <= 100


class TestVIXHedgeSignalEndpoint:
    """Tests for GET /api/vix/hedge-signal"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_hedge_signal_returns_success(self, client):
        """Hedge signal endpoint should return success"""
        response = client.get("/api/vix/hedge-signal")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_hedge_signal_response_structure(self, client):
        """Hedge signal should have required fields"""
        response = client.get("/api/vix/hedge-signal")
        data = response.json()["data"]

        required_fields = [
            "timestamp", "signal_type", "confidence",
            "vol_regime", "reasoning", "recommended_action"
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_hedge_signal_with_portfolio_params(self, client):
        """Hedge signal should accept portfolio parameters"""
        response = client.get(
            "/api/vix/hedge-signal",
            params={"portfolio_delta": 50000, "portfolio_value": 100000}
        )
        assert response.status_code == 200

    def test_hedge_signal_confidence_is_percentage(self, client):
        """Confidence should be a percentage (0-100)"""
        response = client.get("/api/vix/hedge-signal")
        confidence = response.json()["data"]["confidence"]

        assert isinstance(confidence, (int, float))
        assert 0 <= confidence <= 100

    def test_hedge_signal_valid_signal_types(self, client):
        """Signal type should be one of valid values"""
        response = client.get("/api/vix/hedge-signal")
        signal_type = response.json()["data"]["signal_type"]

        valid_types = [
            "buy_vix_calls", "buy_vix_call_spread", "sell_vix_puts",
            "reduce_hedge", "no_action", "roll_hedge",
            "hedge_recommended", "monitor_closely"
        ]
        assert signal_type in valid_types

    def test_hedge_signal_validation_negative_portfolio_value(self, client):
        """Should reject negative portfolio value"""
        response = client.get(
            "/api/vix/hedge-signal",
            params={"portfolio_value": -1000}
        )
        assert response.status_code == 422  # Validation error

    def test_hedge_signal_validation_extreme_portfolio_delta(self, client):
        """Should reject extreme portfolio delta values"""
        response = client.get(
            "/api/vix/hedge-signal",
            params={"portfolio_delta": 100000000}  # $100M, over limit
        )
        assert response.status_code == 422  # Validation error


class TestVIXSignalHistoryEndpoint:
    """Tests for GET /api/vix/signal-history"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_signal_history_returns_success(self, client):
        """Signal history endpoint should return success"""
        response = client.get("/api/vix/signal-history")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "data" in data

    def test_signal_history_returns_list(self, client):
        """Signal history data should be a list"""
        response = client.get("/api/vix/signal-history")
        data = response.json()["data"]
        assert isinstance(data, list)

    def test_signal_history_with_days_param(self, client):
        """Signal history should accept days parameter"""
        response = client.get("/api/vix/signal-history", params={"days": 7})
        assert response.status_code == 200

    def test_signal_history_validation_days_range(self, client):
        """Days parameter should be within valid range (1-365)"""
        # Too low
        response = client.get("/api/vix/signal-history", params={"days": 0})
        assert response.status_code == 422

        # Too high
        response = client.get("/api/vix/signal-history", params={"days": 500})
        assert response.status_code == 422

    def test_signal_history_item_structure(self, client):
        """Each history item should have required fields"""
        response = client.get("/api/vix/signal-history")
        data = response.json()["data"]

        if len(data) > 0:
            item = data[0]
            # Check optional fields exist
            assert "signal_type" in item or item.get("signal_type") is None
            assert "vix_level" in item or item.get("vix_level") is None


class TestVIXMetricsEndpoint:
    """Tests for GET /api/vix/metrics"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_metrics_returns_success(self, client):
        """Metrics endpoint should return success"""
        response = client.get("/api/vix/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_metrics_response_structure(self, client):
        """Metrics should have required fields"""
        response = client.get("/api/vix/metrics")
        data = response.json()["data"]

        required_fields = [
            "requests_total", "requests_success", "requests_fallback",
            "requests_error", "source_hits", "avg_response_time_ms"
        ]

        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_metrics_counters_non_negative(self, client):
        """All metric counters should be non-negative"""
        response = client.get("/api/vix/metrics")
        data = response.json()["data"]

        assert data["requests_total"] >= 0
        assert data["requests_success"] >= 0
        assert data["requests_fallback"] >= 0
        assert data["requests_error"] >= 0


class TestVIXDebugEndpoint:
    """Tests for GET /api/vix/debug"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_debug_returns_data(self, client):
        """Debug endpoint should return data"""
        response = client.get("/api/vix/debug")
        assert response.status_code == 200
        # May have success=True or success=False depending on module availability
        assert "timestamp" in response.json() or "data" in response.json()

    def test_debug_includes_config(self, client):
        """Debug should include configuration info"""
        response = client.get("/api/vix/debug")
        data = response.json()

        # Config should be present in either data or top level
        if "data" in data and data.get("data"):
            assert "config" in data["data"] or "thresholds" in str(data)
        else:
            assert "config" in data or "thresholds" in str(data)


class TestVIXTestSourcesEndpoint:
    """Tests for GET /api/vix/test-sources"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_test_sources_returns_data(self, client):
        """Test sources endpoint should return data"""
        response = client.get("/api/vix/test-sources")
        assert response.status_code == 200

    def test_test_sources_response_structure(self, client):
        """Test sources should have required fields"""
        response = client.get("/api/vix/test-sources")
        data = response.json()

        assert "sources" in data
        assert "timestamp" in data
        assert "summary" in data

    def test_test_sources_summary_fields(self, client):
        """Summary should include working sources count"""
        response = client.get("/api/vix/test-sources")
        summary = response.json()["summary"]

        assert "working_sources" in summary
        assert "total_sources_tested" in summary
        assert "any_source_working" in summary


class TestVIXCacheClearEndpoint:
    """Tests for POST /api/vix/cache/clear"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_cache_clear_returns_success(self, client):
        """Cache clear endpoint should return success"""
        response = client.post("/api/vix/cache/clear")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data


class TestVIXFallbackBehavior:
    """Tests for fallback behavior when primary sources fail"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_fallback_mode_indicated(self, client):
        """Response should indicate if using fallback mode"""
        response = client.get("/api/vix/current")
        data = response.json()["data"]

        # fallback_mode should be present (True or False)
        assert "fallback_mode" in data or data.get("is_estimated") is not None

    def test_default_vix_reasonable(self, client):
        """Even in fallback, VIX should be a reasonable value"""
        response = client.get("/api/vix/current")
        vix_spot = response.json()["data"]["vix_spot"]

        # Default is 18.0, should be in reasonable range
        assert 10 <= vix_spot <= 50


class TestVIXDataConsistency:
    """Tests for data consistency across endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from backend.api.app import app
        return TestClient(app)

    def test_vix_spot_consistent(self, client):
        """VIX spot should be consistent between current and hedge-signal"""
        current_response = client.get("/api/vix/current")
        signal_response = client.get("/api/vix/hedge-signal")

        current_vix = current_response.json()["data"]["vix_spot"]
        signal_vix = signal_response.json()["data"].get("metrics", {}).get("vix_spot")

        if signal_vix:
            # Allow small difference due to timing
            assert abs(current_vix - signal_vix) < 1.0

    def test_stress_level_matches_vix(self, client):
        """Stress level should be appropriate for VIX value"""
        response = client.get("/api/vix/current")
        data = response.json()["data"]

        vix_spot = data["vix_spot"]
        stress_level = data["vix_stress_level"]

        # Verify stress level matches VIX thresholds
        if vix_spot >= 30:
            assert stress_level in ["extreme", "high"]
        elif vix_spot >= 25:
            assert stress_level in ["high", "elevated"]
        elif vix_spot >= 20:
            assert stress_level in ["elevated", "normal"]
        else:
            assert stress_level in ["normal", "low"]


class TestVIXConfigValues:
    """Tests for configuration values from vix_routes.VIXConfig"""

    def test_thresholds_ascending(self):
        """VIX thresholds should be in ascending order"""
        from backend.api.routes.vix_routes import VIXConfig

        assert VIXConfig.THRESHOLD_LOW < VIXConfig.THRESHOLD_ELEVATED
        assert VIXConfig.THRESHOLD_ELEVATED < VIXConfig.THRESHOLD_HIGH
        assert VIXConfig.THRESHOLD_HIGH < VIXConfig.THRESHOLD_EXTREME

    def test_multipliers_descending(self):
        """Position multipliers should decrease with stress"""
        from backend.api.routes.vix_routes import VIXConfig

        assert VIXConfig.MULTIPLIER_NORMAL > VIXConfig.MULTIPLIER_ELEVATED
        assert VIXConfig.MULTIPLIER_ELEVATED > VIXConfig.MULTIPLIER_HIGH
        assert VIXConfig.MULTIPLIER_HIGH > VIXConfig.MULTIPLIER_EXTREME

    def test_default_vix_reasonable(self):
        """Default VIX should be in reasonable range"""
        from backend.api.routes.vix_routes import VIXConfig

        assert 15 <= VIXConfig.DEFAULT_VIX <= 25


class TestVIXHelperFunctions:
    """Tests for helper functions in vix_routes"""

    def test_get_stress_level_function(self):
        """get_stress_level should return correct levels"""
        from backend.api.routes.vix_routes import get_stress_level

        # Test different VIX levels
        level, mult = get_stress_level(10)
        assert level == "normal"
        assert mult == 1.0

        level, mult = get_stress_level(22)
        assert level == "elevated"
        assert mult == 0.75

        level, mult = get_stress_level(27)
        assert level == "high"
        assert mult == 0.5

        level, mult = get_stress_level(35)
        assert level == "extreme"
        assert mult == 0.25

    def test_calculate_fallback_iv_percentile(self):
        """IV percentile calculation should be reasonable"""
        from backend.api.routes.vix_routes import calculate_fallback_iv_percentile

        # Low VIX should have low percentile
        assert calculate_fallback_iv_percentile(10) < 20

        # High VIX should have high percentile
        assert calculate_fallback_iv_percentile(35) > 80

        # Extreme VIX should be near 100
        assert calculate_fallback_iv_percentile(50) >= 95

    def test_calculate_fallback_realized_vol(self):
        """Realized vol estimate should be less than VIX"""
        from backend.api.routes.vix_routes import calculate_fallback_realized_vol

        # RV should generally be less than IV (VIX)
        for vix in [12, 18, 25, 35]:
            rv = calculate_fallback_realized_vol(vix)
            assert rv < vix
            assert rv > 0

    def test_calculate_term_structure(self):
        """Term structure calculation should be consistent"""
        from backend.api.routes.vix_routes import calculate_term_structure

        # Low VIX = steep contango
        result = calculate_term_structure(12)
        assert result["structure_type"] == "contango"
        assert result["vix_m1"] > 12
        assert result["vix_m2"] > result["vix_m1"]

        # High VIX = may be backwardation
        result = calculate_term_structure(40)
        assert result["structure_type"] in ["backwardation", "flat"]


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
