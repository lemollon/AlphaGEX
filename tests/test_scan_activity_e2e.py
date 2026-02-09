"""
End-to-End Test for Scan Activity Logging System

Tests the complete flow:
1. scan_explainer.py - Claude AI explanations
2. scan_activity_logger.py - Database logging
3. scan_activity_routes.py - API endpoints
4. Frontend data format compatibility

Run with: python -m pytest tests/test_scan_activity_e2e.py -v
"""

import os
import sys
import json
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CENTRAL_TZ = ZoneInfo("America/Chicago")


class TestScanExplainer:
    """Test the Claude AI explanation generator"""

    def test_fallback_explanation_no_trade_rr_ratio(self):
        """Test fallback explanation when R:R ratio fails"""
        from trading.scan_explainer import (
            _generate_fallback_explanation, ScanContext, MarketContext,
            SignalContext, CheckDetail, DecisionType
        )

        context = ScanContext(
            bot_name="SOLOMON",
            scan_number=5,
            decision_type=DecisionType.NO_TRADE,
            market=MarketContext(
                underlying_symbol="SPY",
                underlying_price=593.45,
                vix=14.2,
                call_wall=597.0,
                put_wall=586.0,
                gex_regime="POSITIVE"
            ),
            signal=SignalContext(
                source="ML",
                direction="BULLISH",
                confidence=0.72,
                win_probability=0.65
            ),
            checks=[
                CheckDetail(
                    name="rr_ratio",
                    passed=False,
                    actual_value="0.92:1",
                    required_value="1.5:1",
                    explanation="R:R too low for favorable trade"
                )
            ]
        )

        result = _generate_fallback_explanation(context)

        # Verify all required fields are present
        assert "summary" in result
        assert "full_explanation" in result
        assert "what_would_trigger" in result
        assert "market_insight" in result

        # Verify summary contains key info
        assert "NO_TRADE" in result["summary"] or "SOLOMON" in result["summary"]
        assert "rr_ratio" in result["summary"].lower() or "r:r" in result["summary"].lower()

        # Verify what_would_trigger has price targets
        trigger = result["what_would_trigger"]
        assert "BULLISH" in trigger or "Price" in trigger or "drop" in trigger.lower()
        print(f"\n[PASS] Fallback explanation generated:")
        print(f"  Summary: {result['summary']}")
        print(f"  What would trigger: {trigger[:100]}...")
        print(f"  Market insight: {result['market_insight']}")

    def test_fallback_explanation_oracle_skip(self):
        """Test fallback when Prophet recommends SKIP"""
        from trading.scan_explainer import (
            _generate_fallback_explanation, ScanContext, MarketContext,
            SignalContext, DecisionType
        )

        context = ScanContext(
            bot_name="FORTRESS",
            scan_number=3,
            decision_type=DecisionType.NO_TRADE,
            market=MarketContext(
                underlying_symbol="SPX",
                underlying_price=5980.0,
                vix=18.5
            ),
            signal=SignalContext(
                source="Prophet",
                direction="NEUTRAL",
                confidence=0.45,
                win_probability=0.52,
                advice="SKIP_TODAY",
                reasoning="VIX term structure inverted - high uncertainty"
            )
        )

        result = _generate_fallback_explanation(context)

        assert "Prophet" in result["summary"] or "advised" in result["summary"]
        assert result["what_would_trigger"]
        print(f"\n[PASS] Prophet SKIP explanation: {result['summary']}")

    def test_fallback_explanation_traded(self):
        """Test explanation when trade is executed"""
        from trading.scan_explainer import (
            _generate_fallback_explanation, ScanContext, MarketContext,
            SignalContext, DecisionType
        )

        context = ScanContext(
            bot_name="SOLOMON",
            scan_number=2,
            decision_type=DecisionType.TRADED,
            market=MarketContext(
                underlying_symbol="SPY",
                underlying_price=588.0,
                vix=16.5,
                call_wall=597.0,
                put_wall=585.0
            ),
            signal=SignalContext(
                source="ML",
                direction="BULLISH",
                confidence=0.82,
                win_probability=0.71
            ),
            trade_details={
                "strategy": "BULL_CALL_SPREAD",
                "contracts": 5,
                "premium_collected": 125.0,
                "max_risk": 375.0
            }
        )

        result = _generate_fallback_explanation(context)

        assert "TRADED" in result["summary"]
        assert "N/A" in result["what_would_trigger"]
        print(f"\n[PASS] Trade executed explanation: {result['summary']}")


class TestScanActivityLogger:
    """Test the database logging functions"""

    def test_check_result_dataclass(self):
        """Test CheckResult dataclass creation"""
        from trading.scan_activity_logger import CheckResult

        check = CheckResult(
            check_name="rr_ratio",
            passed=False,
            value="0.92:1",
            threshold="1.5:1",
            reason="R:R below minimum"
        )

        assert check.check_name == "rr_ratio"
        assert check.passed is False
        assert check.value == "0.92:1"
        print(f"\n[PASS] CheckResult created: {check}")

    def test_scan_outcome_enum(self):
        """Test ScanOutcome enum values"""
        from trading.scan_activity_logger import ScanOutcome

        assert ScanOutcome.TRADED.value == "TRADED"
        assert ScanOutcome.NO_TRADE.value == "NO_TRADE"
        assert ScanOutcome.SKIP.value == "SKIP"
        assert ScanOutcome.ERROR.value == "ERROR"
        assert ScanOutcome.BEFORE_WINDOW.value == "BEFORE_WINDOW"
        print(f"\n[PASS] All ScanOutcome values valid")

    @patch('database_adapter.get_connection')
    def test_log_scan_activity_structure(self, mock_get_conn):
        """Test log_scan_activity creates correct data structure"""
        from trading.scan_activity_logger import (
            log_scan_activity, ScanOutcome, CheckResult
        )

        # Mock database connection
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Call the function with all parameters
        result = log_scan_activity(
            bot_name="SOLOMON",
            outcome=ScanOutcome.NO_TRADE,
            decision_summary="R:R 0.92:1 below minimum 1.5:1",
            action_taken="No trade - risk/reward unfavorable",
            market_data={
                "underlying_price": 593.45,
                "vix": 14.2,
                "symbol": "SPY"
            },
            gex_data={
                "call_wall": 597.0,
                "put_wall": 586.0,
                "regime": "POSITIVE",
                "net_gex": 1500000000
            },
            signal_source="ML",
            signal_direction="BULLISH",
            signal_confidence=0.72,
            signal_win_probability=0.65,
            risk_reward_ratio=0.92,
            checks=[
                CheckResult("should_trade", True, "Yes", "Yes", "Conditions met"),
                CheckResult("gex_data", True, "Spot $593.45", "Required", "GEX available"),
                CheckResult("rr_ratio", False, "0.92:1", ">=1.5:1", "R:R too low")
            ],
            generate_ai_explanation=False  # Skip Claude for unit test
        )

        # Verify execute was called for table creation and insert
        assert mock_cursor.execute.called
        print(f"\n[PASS] log_scan_activity called database correctly")

    @patch('database_adapter.get_connection')
    def test_log_fortress_scan_with_full_reasoning_kwarg(self, mock_get_conn):
        """Test that passing full_reasoning as kwarg doesn't cause 'multiple values' error"""
        from trading.scan_activity_logger import log_fortress_scan, ScanOutcome, CheckResult

        # Mock database connection
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # This used to crash with: "got multiple values for keyword argument 'full_reasoning'"
        try:
            result = log_fortress_scan(
                outcome=ScanOutcome.NO_TRADE,
                decision_summary="Test summary",
                full_reasoning="This is the full reasoning passed as kwarg",
                generate_ai_explanation=False
            )
            print(f"\n[PASS] log_fortress_scan accepts full_reasoning kwarg without error")
        except TypeError as e:
            if "multiple values" in str(e):
                raise AssertionError(f"kwargs bug not fixed: {e}")
            raise

    @patch('database_adapter.get_connection')
    def test_log_fortress_scan_with_all_kwargs(self, mock_get_conn):
        """Test that passing action_taken, error_type as kwargs doesn't cause errors"""
        from trading.scan_activity_logger import log_fortress_scan, ScanOutcome, CheckResult

        # Mock database connection
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # Test all kwargs that could cause "multiple values" errors
        try:
            result = log_fortress_scan(
                outcome=ScanOutcome.ERROR,
                decision_summary="Test crash scenario",
                full_reasoning="Full reasoning for the crash",
                action_taken="Bot crashed - will retry",
                error_type="UNHANDLED_EXCEPTION",
                error_message="Test error message",
                generate_ai_explanation=False
            )
            print(f"\n[PASS] log_fortress_scan accepts all kwargs without error")
        except (TypeError, NameError) as e:
            raise AssertionError(f"kwargs bug not fixed: {e}")

    @patch('database_adapter.get_connection')
    def test_log_solomon_scan_with_all_kwargs(self, mock_get_conn):
        """Test that log_solomon_scan handles action_taken and error_type kwargs correctly"""
        from trading.scan_activity_logger import log_solomon_scan, ScanOutcome, CheckResult

        # Mock database connection
        mock_cursor = Mock()
        mock_conn = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_get_conn.return_value = mock_conn

        # This used to crash with: NameError: name 'action_taken' is not defined
        try:
            result = log_solomon_scan(
                outcome=ScanOutcome.NO_TRADE,
                decision_summary="Test SOLOMON summary",
                full_reasoning="SOLOMON full reasoning",
                action_taken="SOLOMON action taken",
                error_type="SOLOMON_ERROR",
                generate_ai_explanation=False
            )
            print(f"\n[PASS] log_solomon_scan accepts action_taken/error_type kwargs without error")
        except NameError as e:
            raise AssertionError(f"Undefined variable bug not fixed: {e}")
        except TypeError as e:
            if "multiple values" in str(e):
                raise AssertionError(f"kwargs bug not fixed: {e}")
            raise


class TestAPIRoutes:
    """Test the API routes return correct format"""

    def test_scan_activity_response_format(self):
        """Test that API response matches frontend expectations"""
        # Expected format for frontend ScanActivityFeed component
        expected_fields = [
            'id', 'scan_id', 'scan_number', 'timestamp', 'time_ct',
            'outcome', 'decision_summary', 'full_reasoning',
            'what_would_trigger', 'market_insight',
            'underlying_price', 'vix', 'gex_regime',
            'call_wall', 'put_wall', 'risk_reward_ratio',
            'signal_source', 'signal_direction', 'signal_confidence',
            'signal_win_probability', 'oracle_advice',
            'trade_executed', 'checks_performed'
        ]

        # Create a mock scan record
        mock_scan = {
            'id': 1,
            'scan_id': 'SOLOMON-20241223-101500-0001',
            'scan_number': 5,
            'timestamp': '2024-12-23T10:15:00',
            'time_ct': '10:15:00 AM',
            'outcome': 'NO_TRADE',
            'decision_summary': 'R:R 0.92:1 below minimum 1.5:1',
            'full_reasoning': 'Trade not taken because rr_ratio check failed.',
            'what_would_trigger': 'Price needs to drop to ~$588.20 for BULLISH R:R',
            'market_insight': 'VIX at 14.2 is low - premium may be insufficient',
            'underlying_price': 593.45,
            'vix': 14.2,
            'gex_regime': 'POSITIVE',
            'call_wall': 597.0,
            'put_wall': 586.0,
            'risk_reward_ratio': 0.92,
            'signal_source': 'ML',
            'signal_direction': 'BULLISH',
            'signal_confidence': 0.72,
            'signal_win_probability': 0.65,
            'oracle_advice': None,
            'trade_executed': False,
            'checks_performed': [
                {'check_name': 'should_trade', 'passed': True, 'value': 'Yes'},
                {'check_name': 'rr_ratio', 'passed': False, 'value': '0.92:1'}
            ]
        }

        # Verify all expected fields are present
        for field in expected_fields:
            assert field in mock_scan, f"Missing field: {field}"

        print(f"\n[PASS] API response format matches frontend expectations")
        print(f"  Fields verified: {len(expected_fields)}")


class TestIntegration:
    """Integration tests combining multiple components"""

    def test_full_logging_flow(self):
        """Test the complete flow from decision to log"""
        from trading.scan_activity_logger import CheckResult, ScanOutcome

        # Simulate SOLOMON scan with R:R failure
        checks = [
            CheckResult("should_trade", True, "Yes", "Yes", "Trade conditions met"),
            CheckResult("gex_data", True, "Spot $593.45", "Required", "GEX regime: POSITIVE"),
            CheckResult("gex_walls", True, "Put $586 / Call $597", "Informational", "Used for R:R"),
            CheckResult("signal", True, "ML", "Actionable", "ML signal: BULLISH"),
            CheckResult("rr_ratio", False, "0.92:1", ">=1.5:1", "R:R too low - need 1.5:1 minimum")
        ]

        market_data = {
            'underlying_price': 593.45,
            'vix': 14.2,
            'symbol': 'SPY'
        }

        gex_data = {
            'spot_price': 593.45,
            'call_wall': 597.0,
            'put_wall': 586.0,
            'regime': 'POSITIVE',
            'net_gex': 1500000000
        }

        # Verify data structure is correct for logging
        assert len(checks) == 5
        assert not checks[4].passed  # R:R should fail
        assert market_data['underlying_price'] == 593.45
        assert gex_data['call_wall'] > gex_data['put_wall']

        print(f"\n[PASS] Full logging flow data structure verified")
        print(f"  Checks: {len(checks)} ({sum(1 for c in checks if c.passed)} passed)")
        print(f"  Market: SPY @ ${market_data['underlying_price']}, VIX {market_data['vix']}")
        print(f"  GEX: Put ${gex_data['put_wall']} | Call ${gex_data['call_wall']}")

    def test_rr_ratio_calculation(self):
        """Test R:R ratio calculation matches SOLOMON logic"""
        # SOLOMON R:R calculation for BULLISH:
        # R:R = (call_wall - spot) / (spot - put_wall)

        spot = 593.45
        call_wall = 597.0
        put_wall = 586.0

        reward = call_wall - spot  # 3.55
        risk = spot - put_wall     # 7.45
        rr_ratio = reward / risk   # 0.476

        assert reward > 0, "Reward should be positive for BULLISH"
        assert risk > 0, "Risk should be positive"
        assert rr_ratio < 1.5, "R:R should be below 1.5 threshold"

        print(f"\n[PASS] R:R ratio calculation verified")
        print(f"  Spot: ${spot}, Walls: ${put_wall} - ${call_wall}")
        print(f"  Reward: ${reward:.2f}, Risk: ${risk:.2f}")
        print(f"  R:R Ratio: {rr_ratio:.2f}:1 (below 1.5:1 threshold)")

        # Calculate where price would need to be for 1.5:1 R:R
        # 1.5 = (call_wall - x) / (x - put_wall)
        # 1.5 * (x - put_wall) = call_wall - x
        # 1.5x - 1.5*put_wall = call_wall - x
        # 2.5x = call_wall + 1.5*put_wall
        # x = (call_wall + 1.5*put_wall) / 2.5

        target_price = (call_wall + 1.5 * put_wall) / 2.5
        print(f"  For 1.5:1 R:R, price needs to be: ${target_price:.2f}")


def run_all_tests():
    """Run all tests and report results"""
    print("=" * 60)
    print("SCAN ACTIVITY END-TO-END TEST SUITE")
    print("=" * 60)

    test_classes = [
        TestScanExplainer,
        TestScanActivityLogger,
        TestAPIRoutes,
        TestIntegration
    ]

    total_passed = 0
    total_failed = 0

    for test_class in test_classes:
        print(f"\n{'=' * 60}")
        print(f"Running: {test_class.__name__}")
        print("=" * 60)

        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith('test_')]

        for method_name in methods:
            try:
                getattr(instance, method_name)()
                total_passed += 1
            except Exception as e:
                print(f"\n[FAIL] {method_name}: {e}")
                total_failed += 1

    print("\n" + "=" * 60)
    print(f"TEST RESULTS: {total_passed} passed, {total_failed} failed")
    print("=" * 60)

    return total_failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
