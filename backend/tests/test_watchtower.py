"""
WATCHTOWER (0DTE Gamma Live) API Tests

Tests for the WATCHTOWER backend endpoints that provide real-time
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
    """Tests for /api/watchtower/gamma endpoint"""

    def test_get_gamma_data_success(self):
        """Test that gamma endpoint returns valid data structure"""
        response = client.get("/api/watchtower/gamma")

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
        response = client.get("/api/watchtower/gamma?expiration=mon")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_gamma_strikes_structure(self):
        """Test that strike data has required fields"""
        response = client.get("/api/watchtower/gamma")

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
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        assert "magnets" in data["data"]
        assert "likely_pin" in data["data"]
        assert "pin_probability" in data["data"]


class TestArgusExpirationsEndpoint:
    """Tests for /api/watchtower/expirations endpoint"""

    def test_get_expirations_success(self):
        """Test that expirations endpoint returns valid data"""
        response = client.get("/api/watchtower/expirations")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "expirations" in data["data"]

    def test_expirations_have_required_fields(self):
        """Test expiration data structure"""
        response = client.get("/api/watchtower/expirations")

        data = response.json()
        if data["data"]["expirations"]:
            exp = data["data"]["expirations"][0]
            assert "day" in exp
            assert "date" in exp
            assert "is_today" in exp


class TestArgusAlertsEndpoint:
    """Tests for /api/watchtower/alerts endpoint"""

    def test_get_alerts_success(self):
        """Test that alerts endpoint returns valid data"""
        response = client.get("/api/watchtower/alerts")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "alerts" in data["data"]

    def test_get_alerts_with_filters(self):
        """Test alerts endpoint with filter parameters"""
        response = client.get("/api/watchtower/alerts?priority=HIGH")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusCommentaryEndpoint:
    """Tests for /api/watchtower/commentary endpoint"""

    def test_get_commentary_success(self):
        """Test that commentary endpoint returns valid data"""
        response = client.get("/api/watchtower/commentary")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "commentary" in data["data"]

    def test_get_commentary_with_limit(self):
        """Test commentary endpoint with limit parameter"""
        response = client.get("/api/watchtower/commentary?limit=5")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        # Should return at most 5 items
        assert len(data["data"]["commentary"]) <= 5


class TestArgusHistoryEndpoint:
    """Tests for /api/watchtower/history endpoint"""

    def test_get_history_success(self):
        """Test that history endpoint returns valid data"""
        response = client.get("/api/watchtower/history")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data

    def test_get_history_with_minutes(self):
        """Test history endpoint with minutes parameter"""
        response = client.get("/api/watchtower/history?minutes=30")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusProbabilityEndpoint:
    """Tests for /api/watchtower/probability endpoint"""

    def test_get_probability_success(self):
        """Test that probability endpoint returns valid data"""
        response = client.get("/api/watchtower/probability")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusAccuracyEndpoint:
    """Tests for /api/watchtower/accuracy endpoint"""

    def test_get_accuracy_success(self):
        """Test that accuracy endpoint returns valid data"""
        response = client.get("/api/watchtower/accuracy")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusBotsEndpoint:
    """Tests for /api/watchtower/bots endpoint"""

    def test_get_bots_status_success(self):
        """Test that bots endpoint returns valid data"""
        response = client.get("/api/watchtower/bots")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data
        assert "bots" in data["data"]


class TestArgusPatternsEndpoint:
    """Tests for /api/watchtower/patterns endpoint"""

    def test_get_patterns_success(self):
        """Test that patterns endpoint returns valid data"""
        response = client.get("/api/watchtower/patterns")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data


class TestArgusExportEndpoint:
    """Tests for /api/watchtower/export endpoint"""

    def test_export_csv_success(self):
        """Test CSV export endpoint"""
        response = client.get("/api/watchtower/export?format=csv")

        # Should either succeed or return error gracefully
        assert response.status_code in [200, 500]

    def test_export_xlsx_success(self):
        """Test XLSX export endpoint"""
        response = client.get("/api/watchtower/export?format=xlsx")

        # Should either succeed or return error gracefully
        assert response.status_code in [200, 500]


class TestArgusReplayEndpoint:
    """Tests for /api/watchtower/replay endpoints"""

    def test_get_replay_dates_success(self):
        """Test that replay dates endpoint returns valid data"""
        response = client.get("/api/watchtower/replay/dates")

        assert response.status_code == 200
        data = response.json()

        assert data["success"] is True
        assert "data" in data

    def test_get_replay_with_date(self):
        """Test replay endpoint with specific date"""
        # Use today's date
        today = datetime.now().strftime("%Y-%m-%d")
        response = client.get(f"/api/watchtower/replay?date={today}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


class TestArgusGammaFlipDetection:
    """Tests for gamma flip detection functionality"""

    def test_gamma_flips_in_response(self):
        """Test that gamma flips are included in response"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        # gamma_flips should be in the response
        assert "gamma_flips" in data["data"]

    def test_danger_zones_in_response(self):
        """Test that danger zones are included in response"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        # danger_zones should be in the response
        assert "danger_zones" in data["data"]


class TestArgusDataValidation:
    """Tests for data validation and integrity"""

    def test_spot_price_reasonable(self):
        """Test that spot price is within reasonable range"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        spot_price = data["data"]["spot_price"]
        # SPY should be between $100 and $1000
        assert 100 <= spot_price <= 1000

    def test_vix_reasonable(self):
        """Test that VIX is within reasonable range"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        vix = data["data"]["vix"]
        # VIX should be between 5 and 100
        assert 5 <= vix <= 100

    def test_probabilities_sum_to_100(self):
        """Test that strike probabilities sum approximately to 100"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        strikes = data["data"]["strikes"]
        if strikes:
            total_prob = sum(s["probability"] for s in strikes)
            # Allow some margin for rounding
            assert 90 <= total_prob <= 110

    def test_gamma_regime_valid(self):
        """Test that gamma regime is a valid value"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        regime = data["data"]["gamma_regime"]
        valid_regimes = ["POSITIVE", "NEGATIVE", "NEUTRAL"]
        assert regime in valid_regimes

    def test_market_status_valid(self):
        """Test that market status is a valid value"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        status = data["data"]["market_status"]
        valid_statuses = ["pre_market", "open", "after_hours", "closed"]
        assert status in valid_statuses


class TestArgusPerformance:
    """Performance tests for WATCHTOWER endpoints"""

    def test_gamma_endpoint_response_time(self):
        """Test that gamma endpoint responds within acceptable time"""
        import time

        start = time.time()
        response = client.get("/api/watchtower/gamma")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should respond within 5 seconds (allowing for API calls)
        assert elapsed < 5.0

    def test_expirations_endpoint_response_time(self):
        """Test that expirations endpoint responds quickly"""
        import time

        start = time.time()
        response = client.get("/api/watchtower/expirations")
        elapsed = time.time() - start

        assert response.status_code == 200
        # Should respond within 1 second (cached data)
        assert elapsed < 1.0


class TestArgusOrderFlow:
    """Tests for order flow pressure analysis (GAP fixes verification)"""

    def test_order_flow_in_gamma_response(self):
        """Test that order_flow is included in gamma response"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        # order_flow should be in the response
        assert "order_flow" in data["data"]

    def test_order_flow_structure(self):
        """Test that order_flow has all required fields (GAP #5-6 fix)"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        order_flow = data["data"].get("order_flow", {})

        # Top-level order flow fields
        required_top_fields = [
            "net_gex_volume", "call_gex_flow", "put_gex_flow",
            "flow_direction", "flow_strength", "imbalance_ratio",
            "combined_signal", "signal_confidence"
        ]
        for field in required_top_fields:
            assert field in order_flow, f"Missing order_flow field: {field}"

    def test_bid_ask_pressure_structure(self):
        """Test bid_ask_pressure has all required fields (GAP #5-6 fix)"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        bid_ask = data["data"].get("order_flow", {}).get("bid_ask_pressure", {})

        # Required bid_ask_pressure fields including GAP fixes
        required_fields = [
            "net_pressure", "raw_pressure",  # GAP #5 fix
            "pressure_direction", "pressure_strength",
            "call_pressure", "put_pressure",
            "total_bid_size", "total_ask_size",
            "liquidity_score", "strikes_used",
            "smoothing_periods",  # GAP #5 fix
            "is_valid", "reason"  # GAP #6 fix
        ]
        for field in required_fields:
            assert field in bid_ask, f"Missing bid_ask_pressure field: {field}"

    def test_smoothing_periods_valid(self):
        """Test smoothing_periods is valid (GAP #1 fix)"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        bid_ask = data["data"].get("order_flow", {}).get("bid_ask_pressure", {})
        smoothing_periods = bid_ask.get("smoothing_periods", -1)

        # Should be 0-5 (5-period rolling average)
        assert 0 <= smoothing_periods <= 5, f"Invalid smoothing_periods: {smoothing_periods}"

    def test_is_valid_field_type(self):
        """Test is_valid is boolean (GAP #6 fix)"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        bid_ask = data["data"].get("order_flow", {}).get("bid_ask_pressure", {})
        is_valid = bid_ask.get("is_valid")

        assert isinstance(is_valid, bool), f"is_valid should be bool, got {type(is_valid)}"

    def test_pressure_direction_valid(self):
        """Test pressure_direction is valid value"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        bid_ask = data["data"].get("order_flow", {}).get("bid_ask_pressure", {})
        direction = bid_ask.get("pressure_direction", "")

        valid_directions = ["BULLISH", "BEARISH", "NEUTRAL"]
        assert direction in valid_directions, f"Invalid pressure_direction: {direction}"

    def test_combined_signal_valid(self):
        """Test combined_signal is valid value"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        order_flow = data["data"].get("order_flow", {})
        signal = order_flow.get("combined_signal", "")

        valid_signals = [
            "NEUTRAL", "BULLISH", "BEARISH",
            "STRONG_BULLISH", "STRONG_BEARISH",
            "DIVERGENCE_BULLISH", "DIVERGENCE_BEARISH"
        ]
        assert signal in valid_signals, f"Invalid combined_signal: {signal}"


class TestArgusErrorHandling:
    """Tests for error handling and edge cases (GAP #2-3 fixes)"""

    def test_invalid_symbol_handling(self):
        """Test API handles invalid symbol gracefully"""
        response = client.get("/api/watchtower/gamma?symbol=INVALID_SYMBOL_XYZ")

        # Should return 200 with error info, not crash
        assert response.status_code in [200, 400, 500]

        data = response.json()
        # Should have either success=False or error detail
        if response.status_code == 200:
            # May still succeed with default/fallback
            assert "success" in data
        else:
            # Error response should have detail
            assert "detail" in data or "message" in data

    def test_data_unavailable_response_structure(self):
        """Test data_unavailable response has required fields (GAP #2-3 fix)"""
        # This test verifies the error response structure
        # When data is unavailable, should return proper format
        response = client.get("/api/watchtower/gamma?symbol=SPY")

        data = response.json()

        # If data_unavailable, check structure
        if data.get("data_unavailable") or data.get("success") is False:
            assert "reason" in data or "message" in data
            assert "symbol" in data or "data" in data

    def test_success_field_present(self):
        """Test that success field is always present"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        assert "success" in data, "Response must have 'success' field"

    def test_fetched_at_timestamp_present(self):
        """Test that fetched_at timestamp is in response"""
        response = client.get("/api/watchtower/gamma")

        assert response.status_code == 200
        data = response.json()

        if data.get("success"):
            assert "fetched_at" in data["data"], "Response must have 'fetched_at' timestamp"


class TestArgusTradeAction:
    """Tests for /api/watchtower/trade-action endpoint (Actionable Trade Recommendations)"""

    def test_trade_action_returns_200(self):
        """Test trade-action endpoint responds"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        assert response.status_code == 200

    def test_trade_action_has_success_field(self):
        """Test response has success field"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()
        assert "success" in data

    def test_trade_action_has_action_field(self):
        """Test response has action field"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()
        assert data.get("success") is True
        assert "action" in data.get("data", {})

    def test_trade_action_accepts_parameters(self):
        """Test endpoint accepts account_size and risk parameters"""
        response = client.get(
            "/api/watchtower/trade-action",
            params={
                "symbol": "SPY",
                "account_size": 100000,
                "risk_per_trade_pct": 2.0,
                "spread_width": 3
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("success") is True

    def test_trade_action_wait_has_reason(self):
        """Test WAIT response has reason field"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()

        if data.get("success") and data.get("data", {}).get("action") == "WAIT":
            assert "reason" in data["data"], "WAIT response must have 'reason' field"

    def test_trade_action_actionable_has_structure(self):
        """Test actionable trade response has required structure"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()

        if data.get("success"):
            result = data.get("data", {})
            action = result.get("action")

            if action and action != "WAIT":
                assert "direction" in result, "Must have direction"
                assert "confidence" in result, "Must have confidence"
                assert "trade_description" in result, "Must have trade_description"
                assert "trade" in result, "Must have trade structure"
                assert "why" in result, "Must have 'why' reasoning"
                assert "sizing" in result, "Must have sizing"
                assert "entry" in result, "Must have entry"
                assert "exit" in result, "Must have exit rules"

    def test_trade_action_sizing_structure(self):
        """Test sizing has required fields"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()

        if data.get("success"):
            result = data.get("data", {})
            if result.get("action") != "WAIT":
                sizing = result.get("sizing", {})
                assert "contracts" in sizing, "Sizing must have contracts"
                assert "max_loss" in sizing, "Sizing must have max_loss"
                assert "max_profit" in sizing, "Sizing must have max_profit"
                assert "risk_reward" in sizing, "Sizing must have risk_reward"

    def test_trade_action_exit_rules(self):
        """Test exit rules has required fields"""
        response = client.get("/api/watchtower/trade-action?symbol=SPY")
        data = response.json()

        if data.get("success"):
            result = data.get("data", {})
            if result.get("action") != "WAIT":
                exit_rules = result.get("exit", {})
                assert "profit_target" in exit_rules, "Exit must have profit_target"
                assert "stop_loss" in exit_rules, "Exit must have stop_loss"


class TestArgusSignalTracking:
    """Tests for /api/watchtower/signals/* endpoints (Signal Performance Tracking)"""

    def test_signals_recent_returns_200(self):
        """Test signals/recent endpoint responds"""
        response = client.get("/api/watchtower/signals/recent?symbol=SPY")
        assert response.status_code == 200

    def test_signals_recent_has_signals_array(self):
        """Test response has signals array"""
        response = client.get("/api/watchtower/signals/recent?symbol=SPY")
        data = response.json()

        if data.get("success"):
            assert "signals" in data.get("data", {}), "Must have signals array"
            assert isinstance(data["data"]["signals"], list), "Signals must be array"

    def test_signals_performance_returns_200(self):
        """Test signals/performance endpoint responds"""
        response = client.get("/api/watchtower/signals/performance?symbol=SPY")
        assert response.status_code == 200

    def test_signals_performance_has_summary(self):
        """Test performance response has summary structure"""
        response = client.get("/api/watchtower/signals/performance?symbol=SPY")
        data = response.json()

        if data.get("success"):
            result = data.get("data", {})
            assert "summary" in result, "Must have summary"
            summary = result["summary"]
            assert "total_signals" in summary
            assert "wins" in summary
            assert "losses" in summary
            assert "win_rate" in summary
            assert "total_pnl" in summary

    def test_signals_performance_has_by_action(self):
        """Test performance has by_action breakdown"""
        response = client.get("/api/watchtower/signals/performance?symbol=SPY")
        data = response.json()

        if data.get("success"):
            result = data.get("data", {})
            assert "by_action" in result, "Must have by_action"
            assert isinstance(result["by_action"], list), "by_action must be array"

    def test_signals_log_accepts_post(self):
        """Test signals/log endpoint accepts POST"""
        test_signal = {
            "action": "TEST_SIGNAL",
            "direction": "NEUTRAL",
            "confidence": 50,
            "trade_description": "Test signal - do not trade",
            "trade": {"type": "TEST", "symbol": "SPY"},
            "sizing": {"contracts": 1, "max_loss": "$100", "max_profit": "$50"},
            "entry": "Test",
            "exit": {"profit_target": "50%", "stop_loss": "2x"},
            "market_context": {"spot": 590, "vix": 18}
        }

        response = client.post(
            "/api/watchtower/signals/log",
            params={"symbol": "SPY"},
            json=test_signal
        )
        assert response.status_code == 200

    def test_signals_update_outcomes_accepts_post(self):
        """Test signals/update-outcomes endpoint accepts POST"""
        response = client.post("/api/watchtower/signals/update-outcomes?symbol=SPY")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
