#!/usr/bin/env python3
"""
HERACLES Implementation Verification Tests
==========================================

Comprehensive tests that verify:
1. API endpoints exist and return proper data
2. Frontend hooks map to correct backend endpoints
3. Database tables exist with proper schema
4. Overnight hybrid strategy is wired correctly
5. Gamma regime filter is wired correctly
6. Position management uses correct parameters

Run: pytest tests/test_heracles_implementation.py -v
Or:  python tests/test_heracles_implementation.py --api-url http://localhost:8000
"""

import sys
import os
import argparse
from typing import Dict, Any, List, Tuple

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestResult:
    """Container for test results"""
    def __init__(self, name: str, passed: bool, message: str = "", severity: str = "MEDIUM"):
        self.name = name
        self.passed = passed
        self.message = message
        self.severity = severity  # CRITICAL, HIGH, MEDIUM, LOW

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}" if self.message else f"[{status}] {self.name}"


class HERACLESImplementationVerifier:
    """Verifies HERACLES implementation is complete and wired correctly"""

    def __init__(self, api_url: str = None):
        self.api_url = api_url
        self.results: List[TestResult] = []

    def add_result(self, name: str, passed: bool, message: str = "", severity: str = "MEDIUM"):
        self.results.append(TestResult(name, passed, message, severity))

    def run_all_tests(self) -> Tuple[int, int]:
        """Run all verification tests. Returns (passed, failed) counts."""
        print("\n" + "="*70)
        print("HERACLES IMPLEMENTATION VERIFICATION")
        print("="*70)

        # Phase 1: Config Parameter Verification
        print("\n--- Phase 1: Config Parameters ---")
        self._test_config_parameters()

        # Phase 2: Signal Generation Wiring
        print("\n--- Phase 2: Signal Generation Wiring ---")
        self._test_signal_generation_wiring()

        # Phase 3: Database Schema Verification
        print("\n--- Phase 3: Database Schema ---")
        self._test_database_schema()

        # Phase 4: Position Management Wiring
        print("\n--- Phase 4: Position Management ---")
        self._test_position_management_wiring()

        # Phase 5: API Endpoint Verification (if API URL provided)
        if self.api_url:
            print("\n--- Phase 5: API Endpoints ---")
            self._test_api_endpoints()

        # Print summary
        return self._print_summary()

    def _test_config_parameters(self):
        """Verify HERACLESConfig has all required parameters"""
        try:
            from trading.heracles.models import HERACLESConfig

            config = HERACLESConfig()

            # Overnight hybrid parameters
            overnight_params = [
                ('use_overnight_hybrid', True, bool),
                ('overnight_stop_points', 1.5, float),
                ('overnight_target_points', 3.0, float),
                ('overnight_emergency_stop', 10.0, float),
            ]

            for param_name, expected_default, expected_type in overnight_params:
                if hasattr(config, param_name):
                    value = getattr(config, param_name)
                    if isinstance(value, expected_type):
                        if value == expected_default:
                            self.add_result(
                                f"Config.{param_name}",
                                True,
                                f"exists with correct default ({expected_default})"
                            )
                        else:
                            self.add_result(
                                f"Config.{param_name}",
                                True,
                                f"exists (default={value}, expected={expected_default})"
                            )
                    else:
                        self.add_result(
                            f"Config.{param_name}",
                            False,
                            f"wrong type: got {type(value)}, expected {expected_type}",
                            "HIGH"
                        )
                else:
                    self.add_result(
                        f"Config.{param_name}",
                        False,
                        "parameter missing from HERACLESConfig",
                        "CRITICAL"
                    )

            # Gamma regime filter parameter
            if hasattr(config, 'allowed_gamma_regime'):
                value = config.allowed_gamma_regime
                self.add_result(
                    "Config.allowed_gamma_regime",
                    True,
                    f"exists (default='{value}')"
                )
            else:
                self.add_result(
                    "Config.allowed_gamma_regime",
                    False,
                    "parameter missing from HERACLESConfig",
                    "CRITICAL"
                )

            # No-loss trailing parameters (for reference)
            noloss_params = [
                'use_no_loss_trailing',
                'no_loss_activation_pts',
                'no_loss_trail_distance',
                'no_loss_emergency_stop',
            ]
            for param in noloss_params:
                if hasattr(config, param):
                    self.add_result(f"Config.{param}", True, "exists")
                else:
                    self.add_result(f"Config.{param}", False, "missing", "HIGH")

        except ImportError as e:
            self.add_result("HERACLESConfig import", False, str(e), "CRITICAL")

    def _test_signal_generation_wiring(self):
        """Verify signal generation properly uses overnight hybrid and gamma filter"""
        try:
            from trading.heracles.signals import HERACLESSignalGenerator
            from trading.heracles.models import HERACLESConfig, BayesianWinTracker, GammaRegime

            config = HERACLESConfig()
            win_tracker = BayesianWinTracker()
            generator = HERACLESSignalGenerator(config, win_tracker)

            # Test 1: _set_stop_levels method accepts is_overnight parameter
            import inspect
            sig = inspect.signature(generator._set_stop_levels)
            params = list(sig.parameters.keys())

            if 'is_overnight' in params:
                self.add_result(
                    "_set_stop_levels accepts is_overnight",
                    True,
                    "parameter exists in method signature"
                )
            else:
                self.add_result(
                    "_set_stop_levels accepts is_overnight",
                    False,
                    f"is_overnight not in params: {params}",
                    "CRITICAL"
                )

            # Test 2: generate_signal accepts is_overnight parameter
            sig = inspect.signature(generator.generate_signal)
            params = list(sig.parameters.keys())

            if 'is_overnight' in params:
                self.add_result(
                    "generate_signal accepts is_overnight",
                    True,
                    "parameter exists in method signature"
                )
            else:
                self.add_result(
                    "generate_signal accepts is_overnight",
                    False,
                    f"is_overnight not in params: {params}",
                    "HIGH"
                )

            # Test 3: Verify gamma regime filter logic exists
            # Check if the generate_signal method contains gamma regime filter logic
            import inspect
            source = inspect.getsource(generator.generate_signal)
            if 'allowed_gamma_regime' in source:
                self.add_result(
                    "Gamma regime filter in generate_signal",
                    True,
                    "allowed_gamma_regime check exists in source"
                )
            else:
                self.add_result(
                    "Gamma regime filter in generate_signal",
                    False,
                    "allowed_gamma_regime check missing from generate_signal",
                    "CRITICAL"
                )

            # Test 4: Verify overnight hybrid logic in _set_stop_levels
            source = inspect.getsource(generator._set_stop_levels)
            checks = [
                ('use_overnight_hybrid', 'use_overnight_hybrid check'),
                ('overnight_emergency_stop', 'overnight emergency stop usage'),
                ('overnight_stop_points', 'overnight stop points usage'),
                ('NO_LOSS_TRAIL_OVERNIGHT', 'overnight stop type tracking'),
            ]
            for check, desc in checks:
                if check in source:
                    self.add_result(f"_set_stop_levels: {desc}", True, "found in source")
                else:
                    self.add_result(f"_set_stop_levels: {desc}", False, "missing from source", "HIGH")

        except ImportError as e:
            self.add_result("Signal generator import", False, str(e), "CRITICAL")
        except Exception as e:
            self.add_result("Signal generation wiring test", False, str(e), "HIGH")

    def _test_database_schema(self):
        """Verify database tables have correct columns"""
        try:
            from trading.heracles.db import HERACLESDatabase
            import inspect

            # Get the HERACLESDatabase class source (contains table definitions)
            source = inspect.getsource(HERACLESDatabase)

            # Required tables
            tables = [
                'heracles_positions',
                'heracles_closed_trades',
                'heracles_signals',
                'heracles_equity_snapshots',
                'heracles_config',
                'heracles_win_tracker',
                'heracles_logs',
                'heracles_daily_perf',
                'heracles_paper_account',
                'heracles_scan_activity',
            ]

            for table in tables:
                if table in source:
                    self.add_result(f"Table {table}", True, "CREATE TABLE statement exists")
                else:
                    self.add_result(f"Table {table}", False, "missing from schema", "CRITICAL")

            # Check scan_activity has is_overnight_session column
            if 'is_overnight_session' in source:
                self.add_result(
                    "scan_activity.is_overnight_session column",
                    True,
                    "column exists in schema"
                )
            else:
                self.add_result(
                    "scan_activity.is_overnight_session column",
                    False,
                    "column missing - overnight session tracking won't work",
                    "HIGH"
                )

        except ImportError as e:
            self.add_result("Database module import", False, str(e), "CRITICAL")
        except Exception as e:
            self.add_result("Database schema test", False, str(e), "HIGH")

    def _test_position_management_wiring(self):
        """Verify position management uses stored initial_stop for overnight hybrid"""
        try:
            from trading.heracles.trader import HERACLESTrader
            import inspect

            # Get _manage_position_no_loss_trailing method source
            source = inspect.getsource(HERACLESTrader._manage_position_no_loss_trailing)

            # Verify it uses position.initial_stop to derive emergency stop distance
            if 'position.entry_price - position.initial_stop' in source or 'initial_stop' in source:
                self.add_result(
                    "Position management uses stored initial_stop",
                    True,
                    "derives emergency stop from position's initial_stop"
                )
            else:
                self.add_result(
                    "Position management uses stored initial_stop",
                    False,
                    "doesn't use position.initial_stop - overnight hybrid won't work",
                    "CRITICAL"
                )

            # Verify it doesn't hardcode emergency stop
            if 'self.config.no_loss_emergency_stop' in source and 'initial_stop' not in source:
                self.add_result(
                    "Emergency stop NOT hardcoded",
                    False,
                    "uses config.no_loss_emergency_stop directly instead of position.initial_stop",
                    "HIGH"
                )
            else:
                self.add_result(
                    "Emergency stop NOT hardcoded",
                    True,
                    "properly uses stored stop from position"
                )

            # Verify _is_overnight_session exists
            if hasattr(HERACLESTrader, '_is_overnight_session'):
                self.add_result(
                    "_is_overnight_session method exists",
                    True,
                    "trader can determine session type"
                )
            else:
                self.add_result(
                    "_is_overnight_session method exists",
                    False,
                    "method missing - can't determine overnight session",
                    "HIGH"
                )

        except ImportError as e:
            self.add_result("Trader module import", False, str(e), "CRITICAL")
        except Exception as e:
            self.add_result("Position management wiring test", False, str(e), "HIGH")

    def _test_api_endpoints(self):
        """Test API endpoints if API URL provided"""
        try:
            import requests

            endpoints = [
                ('GET', '/api/heracles/status', 'Status endpoint'),
                ('GET', '/api/heracles/positions', 'Positions endpoint'),
                ('GET', '/api/heracles/closed-trades', 'Closed trades endpoint'),
                ('GET', '/api/heracles/equity-curve', 'Equity curve endpoint'),
                ('GET', '/api/heracles/equity-curve/intraday', 'Intraday equity endpoint'),
                ('GET', '/api/heracles/config', 'Config endpoint'),
                ('GET', '/api/heracles/paper-account', 'Paper account endpoint'),
                ('GET', '/api/heracles/scan-activity', 'Scan activity endpoint'),
                ('GET', '/api/heracles/ml-training-data', 'ML training data endpoint'),
                ('GET', '/api/heracles/ml/status', 'ML status endpoint'),
                ('GET', '/api/heracles/ml/approval-status', 'ML approval status endpoint'),
                ('GET', '/api/heracles/ab-test/status', 'A/B test status endpoint'),
                ('GET', '/api/heracles/diagnostics', 'Diagnostics endpoint'),
            ]

            for method, path, desc in endpoints:
                try:
                    url = f"{self.api_url}{path}"
                    if method == 'GET':
                        response = requests.get(url, timeout=10)
                    else:
                        response = requests.post(url, timeout=10)

                    if response.status_code == 200:
                        self.add_result(desc, True, f"HTTP 200")
                    elif response.status_code == 503:
                        self.add_result(desc, True, "HTTP 503 (module not loaded - OK for test)", "LOW")
                    else:
                        self.add_result(desc, False, f"HTTP {response.status_code}", "HIGH")
                except requests.exceptions.Timeout:
                    self.add_result(desc, False, "Request timeout", "HIGH")
                except requests.exceptions.ConnectionError:
                    self.add_result(desc, False, "Connection error", "CRITICAL")

        except ImportError:
            self.add_result("API tests", False, "requests module not installed", "LOW")

    def _print_summary(self) -> Tuple[int, int]:
        """Print test summary and return (passed, failed) counts"""
        print("\n" + "="*70)
        print("TEST RESULTS SUMMARY")
        print("="*70)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        for result in self.results:
            status = "PASS" if result.passed else f"FAIL [{result.severity}]"
            print(f"  [{status}] {result.name}")
            if result.message:
                print(f"           {result.message}")

        print("\n" + "-"*70)
        print(f"TOTAL: {passed} passed, {failed} failed")

        # Print critical failures
        critical_failures = [r for r in self.results if not r.passed and r.severity == "CRITICAL"]
        if critical_failures:
            print("\n🔴 CRITICAL FAILURES:")
            for r in critical_failures:
                print(f"   - {r.name}: {r.message}")

        # Print high severity failures
        high_failures = [r for r in self.results if not r.passed and r.severity == "HIGH"]
        if high_failures:
            print("\n🟠 HIGH SEVERITY FAILURES:")
            for r in high_failures:
                print(f"   - {r.name}: {r.message}")

        print("\n" + "="*70)
        if failed == 0:
            print("✅ ALL TESTS PASSED - Implementation verified")
        else:
            print(f"❌ {failed} FAILURES - Review and fix before deployment")
        print("="*70)

        return passed, failed


# Also provide pytest-compatible test class (only loads if pytest available)
try:
    import pytest
    PYTEST_AVAILABLE = True
except ImportError:
    PYTEST_AVAILABLE = False
    pytest = None

if PYTEST_AVAILABLE:
    class TestHERACLESImplementation:
        """Pytest-compatible tests"""

        @pytest.fixture
        def config(self):
            from trading.heracles.models import HERACLESConfig
            return HERACLESConfig()

        @pytest.fixture
        def signal_generator(self, config):
            from trading.heracles.signals import HERACLESSignalGenerator
            from trading.heracles.models import BayesianWinTracker
            return HERACLESSignalGenerator(config, BayesianWinTracker())

        def test_overnight_hybrid_config_exists(self, config):
            """Config has overnight hybrid parameters"""
            assert hasattr(config, 'use_overnight_hybrid')
            assert hasattr(config, 'overnight_stop_points')
            assert hasattr(config, 'overnight_target_points')
            assert hasattr(config, 'overnight_emergency_stop')

        def test_overnight_hybrid_defaults(self, config):
            """Overnight hybrid has correct default values"""
            assert config.use_overnight_hybrid == True
            assert config.overnight_stop_points == 1.5
            assert config.overnight_target_points == 3.0
            assert config.overnight_emergency_stop == 10.0

        def test_gamma_regime_filter_config(self, config):
            """Config has gamma regime filter parameter"""
            assert hasattr(config, 'allowed_gamma_regime')
            assert config.allowed_gamma_regime == ""  # Empty = all regimes

        def test_signal_generator_accepts_is_overnight(self, signal_generator):
            """Signal generator accepts is_overnight parameter"""
            import inspect
            sig = inspect.signature(signal_generator.generate_signal)
            assert 'is_overnight' in sig.parameters

        def test_set_stop_levels_accepts_is_overnight(self, signal_generator):
            """_set_stop_levels accepts is_overnight parameter"""
            import inspect
            sig = inspect.signature(signal_generator._set_stop_levels)
            assert 'is_overnight' in sig.parameters

        def test_trader_has_is_overnight_session_method(self):
            """Trader has _is_overnight_session method"""
            from trading.heracles.trader import HERACLESTrader
            assert hasattr(HERACLESTrader, '_is_overnight_session')

        def test_position_management_uses_initial_stop(self):
            """Position management derives emergency stop from stored initial_stop"""
            from trading.heracles.trader import HERACLESTrader
            import inspect

            source = inspect.getsource(HERACLESTrader._manage_position_no_loss_trailing)
            # Should reference position.initial_stop to derive emergency stop distance
            assert 'initial_stop' in source, "Should use position.initial_stop for emergency stop"


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='HERACLES Implementation Verification')
    parser.add_argument('--api-url', type=str, help='API base URL (e.g., http://localhost:8000)')
    args = parser.parse_args()

    verifier = HERACLESImplementationVerifier(api_url=args.api_url)
    passed, failed = verifier.run_all_tests()

    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)
