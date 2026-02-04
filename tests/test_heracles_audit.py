#!/usr/bin/env python3
"""
HERACLES Implementation Verification Audit
==========================================

Comprehensive test suite to verify:
1. Frontend → Backend wiring
2. Backend → Database wiring
3. Feature completeness
4. New max loss rule implementation

Run: python tests/test_heracles_audit.py --api-url https://your-app.render.com
"""

import argparse
import sys
import json
from datetime import datetime

# Only dependency: requests
try:
    import requests
except ImportError:
    print("ERROR: Please install requests: pip install requests")
    sys.exit(1)


class HERACLESAuditTester:
    """Comprehensive HERACLES implementation tester"""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip('/')
        self.results = []
        self.passed = 0
        self.failed = 0

    def log(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        status = "PASS" if passed else "FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"[{status}] {test_name}" + (f" - {details}" if details else ""))

    def _get(self, endpoint: str, timeout: int = 30) -> dict:
        """Make GET request"""
        try:
            url = f"{self.api_url}{endpoint}"
            response = requests.get(url, timeout=timeout)
            return {
                "status_code": response.status_code,
                "data": response.json() if response.text else None,
                "error": None
            }
        except Exception as e:
            return {
                "status_code": 0,
                "data": None,
                "error": str(e)
            }

    def _post(self, endpoint: str, data: dict = None, timeout: int = 30) -> dict:
        """Make POST request"""
        try:
            url = f"{self.api_url}{endpoint}"
            response = requests.post(url, json=data, timeout=timeout)
            return {
                "status_code": response.status_code,
                "data": response.json() if response.text else None,
                "error": None
            }
        except Exception as e:
            return {
                "status_code": 0,
                "data": None,
                "error": str(e)
            }

    # ==================================================================
    # PHASE 1: API Endpoint Tests
    # ==================================================================

    def test_api_endpoints(self):
        """Test all HERACLES API endpoints exist and respond"""
        print("\n" + "=" * 60)
        print("PHASE 1: API ENDPOINT TESTS")
        print("=" * 60)

        # Core endpoints (must work)
        core_endpoints = [
            ("/api/heracles/status", "GET", "Bot status"),
            ("/api/heracles/positions", "GET", "Open positions"),
            ("/api/heracles/closed-trades", "GET", "Trade history"),
            ("/api/heracles/equity-curve", "GET", "Historical equity"),
            ("/api/heracles/equity-curve/intraday", "GET", "Intraday equity"),
            ("/api/heracles/performance", "GET", "Performance stats"),
            ("/api/heracles/config", "GET", "Configuration"),
            ("/api/heracles/logs", "GET", "Activity logs"),
            ("/api/heracles/signals/recent", "GET", "Recent signals"),
            ("/api/heracles/scan-activity", "GET", "Scan activity"),
        ]

        for endpoint, method, description in core_endpoints:
            result = self._get(endpoint)
            if result["error"]:
                self.log(f"API {method} {endpoint}", False, f"Error: {result['error']}")
            elif result["status_code"] == 200:
                self.log(f"API {method} {endpoint}", True, description)
            elif result["status_code"] == 503:
                self.log(f"API {method} {endpoint}", False, "Module not available (503)")
            else:
                self.log(f"API {method} {endpoint}", False, f"Status {result['status_code']}")

        # ML endpoints
        ml_endpoints = [
            ("/api/heracles/ml/status", "GET", "ML model status"),
            ("/api/heracles/ml/feature-importance", "GET", "Feature importance"),
            ("/api/heracles/ml/approval-status", "GET", "ML approval status"),
            ("/api/heracles/ml-training-data", "GET", "ML training data"),
        ]

        print("\n--- ML Endpoints ---")
        for endpoint, method, description in ml_endpoints:
            result = self._get(endpoint)
            if result["error"]:
                self.log(f"API {method} {endpoint}", False, f"Error: {result['error']}")
            elif result["status_code"] == 200:
                self.log(f"API {method} {endpoint}", True, description)
            else:
                self.log(f"API {method} {endpoint}", False, f"Status {result['status_code']}")

        # A/B Test endpoints
        ab_endpoints = [
            ("/api/heracles/ab-test/status", "GET", "A/B test status"),
            ("/api/heracles/ab-test/results", "GET", "A/B test results"),
        ]

        print("\n--- A/B Test Endpoints ---")
        for endpoint, method, description in ab_endpoints:
            result = self._get(endpoint)
            if result["error"]:
                self.log(f"API {method} {endpoint}", False, f"Error: {result['error']}")
            elif result["status_code"] == 200:
                self.log(f"API {method} {endpoint}", True, description)
            else:
                self.log(f"API {method} {endpoint}", False, f"Status {result['status_code']}")

    # ==================================================================
    # PHASE 2: Data Contract Tests
    # ==================================================================

    def test_data_contracts(self):
        """Verify API response shapes match frontend expectations"""
        print("\n" + "=" * 60)
        print("PHASE 2: DATA CONTRACT TESTS")
        print("=" * 60)

        # Test /status response shape
        result = self._get("/api/heracles/status")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]

            # Check required fields
            required_fields = ["market_open", "mode", "symbol", "config", "positions", "performance"]
            missing = [f for f in required_fields if f not in data]
            if missing:
                self.log("Status response has required fields", False, f"Missing: {missing}")
            else:
                self.log("Status response has required fields", True)

            # Check config has new max_unrealized_loss_pts
            config = data.get("config", {})
            if "max_unrealized_loss_pts" in config:
                self.log("Config has max_unrealized_loss_pts", True, f"Value: {config['max_unrealized_loss_pts']}")
            else:
                self.log("Config has max_unrealized_loss_pts", False, "Missing from config")

            # Check no_loss_activation_pts is updated
            if "no_loss_activation_pts" in config:
                value = config["no_loss_activation_pts"]
                if value == 1.5:
                    self.log("no_loss_activation_pts is 1.5 (updated)", True)
                else:
                    self.log("no_loss_activation_pts is 1.5 (updated)", False, f"Got {value}, expected 1.5")
            else:
                self.log("no_loss_activation_pts exists", False, "Missing from config")
        else:
            self.log("Status endpoint returns data", False, f"Status: {result['status_code']}")

        # Test /closed-trades response shape
        result = self._get("/api/heracles/closed-trades?limit=10")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]
            required = ["trades", "count", "today_summary"]
            missing = [f for f in required if f not in data]
            if missing:
                self.log("Closed trades response shape", False, f"Missing: {missing}")
            else:
                self.log("Closed trades response shape", True)

                # Check if loss_analysis columns exist in trades
                trades = data.get("trades", [])
                if trades:
                    trade = trades[0]
                    loss_fields = ["loss_analysis", "mfe_points", "mae_points", "was_profitable_before_loss"]
                    has_loss_fields = any(f in trade for f in loss_fields)
                    self.log("Trades have loss analysis fields", has_loss_fields)
        else:
            self.log("Closed trades endpoint returns data", False)

        # Test /scan-activity response shape
        result = self._get("/api/heracles/scan-activity?limit=10")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]
            required = ["scans", "count", "summary"]
            missing = [f for f in required if f not in data]
            if missing:
                self.log("Scan activity response shape", False, f"Missing: {missing}")
            else:
                self.log("Scan activity response shape", True)
        else:
            self.log("Scan activity endpoint returns data", False)

        # Test /equity-curve response
        result = self._get("/api/heracles/equity-curve?days=7")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]
            required = ["equity_curve", "points", "days"]
            missing = [f for f in required if f not in data]
            if missing:
                self.log("Equity curve response shape", False, f"Missing: {missing}")
            else:
                self.log("Equity curve response shape", True)
        else:
            self.log("Equity curve endpoint returns data", False)

    # ==================================================================
    # PHASE 3: Feature Implementation Tests
    # ==================================================================

    def test_feature_implementation(self):
        """Verify key features are properly implemented"""
        print("\n" + "=" * 60)
        print("PHASE 3: FEATURE IMPLEMENTATION TESTS")
        print("=" * 60)

        # Test diagnostics endpoint (shows all system info)
        result = self._get("/api/heracles/diagnostics")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]

            # Check GEX data availability
            gex_data = data.get("gex_data", {})
            if gex_data.get("available"):
                self.log("GEX data is available", True)
            else:
                warning = gex_data.get("warning", "No warning")
                self.log("GEX data is available", False, warning)

            # Check dynamic stop calculation
            dynamic_stop = data.get("dynamic_stop", {})
            if dynamic_stop.get("enabled"):
                self.log("Dynamic stop calculation works", True, f"Current: {dynamic_stop.get('current_dynamic_stop_pts')} pts")
            else:
                self.log("Dynamic stop calculation works", False, dynamic_stop.get("error", ""))

            # Check market data
            market_data = data.get("market_data", {})
            if market_data.get("available"):
                self.log("Market data (quotes) available", True, f"Last: {market_data.get('last')}")
            else:
                self.log("Market data (quotes) available", False)

            # Check database connectivity
            db_status = data.get("database", {})
            if db_status.get("connected"):
                self.log("Database connected", True)
            else:
                self.log("Database connected", False, db_status.get("error", ""))

        else:
            self.log("Diagnostics endpoint works", False, f"Status: {result['status_code']}")

        # Test ML status
        result = self._get("/api/heracles/ml/status")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]
            self.log("ML status endpoint works", True)

            if data.get("model_trained"):
                self.log("ML model is trained", True, f"Accuracy: {data.get('accuracy', 'N/A')}")
            else:
                samples = data.get("samples_available", 0)
                self.log("ML model is trained", False, f"Samples available: {samples}")
        else:
            self.log("ML status endpoint works", False)

        # Test A/B test status
        result = self._get("/api/heracles/ab-test/status")
        if result["status_code"] == 200 and result["data"]:
            data = result["data"]
            enabled = data.get("ab_test_enabled", False)
            self.log("A/B test status endpoint works", True, f"Enabled: {enabled}")
        else:
            self.log("A/B test status endpoint works", False)

    # ==================================================================
    # PHASE 4: Max Loss Rule Verification
    # ==================================================================

    def test_max_loss_rule(self):
        """Verify the new max loss rule is properly implemented"""
        print("\n" + "=" * 60)
        print("PHASE 4: MAX LOSS RULE VERIFICATION")
        print("=" * 60)

        # Get config to check max_unrealized_loss_pts
        result = self._get("/api/heracles/config")
        if result["status_code"] == 200 and result["data"]:
            config = result["data"].get("config", {})

            # Check max_unrealized_loss_pts exists and has correct value
            max_loss = config.get("max_unrealized_loss_pts")
            if max_loss is not None:
                self.log("max_unrealized_loss_pts in config", True, f"Value: {max_loss}")
                if max_loss == 8.0:
                    self.log("max_unrealized_loss_pts = 8.0 (expected)", True)
                else:
                    self.log("max_unrealized_loss_pts = 8.0 (expected)", False, f"Got {max_loss}")
            else:
                self.log("max_unrealized_loss_pts in config", False, "Not found in config")

            # Check no_loss_activation_pts is updated
            activation = config.get("no_loss_activation_pts")
            if activation is not None:
                self.log("no_loss_activation_pts in config", True, f"Value: {activation}")
                if activation == 1.5:
                    self.log("no_loss_activation_pts = 1.5 (updated from 3.0)", True)
                elif activation == 3.0:
                    self.log("no_loss_activation_pts = 1.5 (updated from 3.0)", False, "Still 3.0 - NOT updated!")
                else:
                    self.log("no_loss_activation_pts = 1.5 (updated from 3.0)", False, f"Got {activation}")
            else:
                self.log("no_loss_activation_pts in config", False, "Not found")

            # Check no_loss_emergency_stop
            emergency = config.get("no_loss_emergency_stop")
            if emergency is not None:
                self.log("no_loss_emergency_stop in config", True, f"Value: {emergency}")
            else:
                self.log("no_loss_emergency_stop in config", False)

        else:
            self.log("Config endpoint returns data", False)

    # ==================================================================
    # PHASE 5: Loss Analysis Verification
    # ==================================================================

    def test_loss_analysis(self):
        """Verify loss analysis columns are populated in closed trades"""
        print("\n" + "=" * 60)
        print("PHASE 5: LOSS ANALYSIS VERIFICATION")
        print("=" * 60)

        result = self._get("/api/heracles/closed-trades?limit=100")
        if result["status_code"] == 200 and result["data"]:
            trades = result["data"].get("trades", [])

            if not trades:
                self.log("Has closed trades for analysis", False, "No trades found")
                return

            self.log("Has closed trades for analysis", True, f"Found {len(trades)} trades")

            # Check loss analysis fields
            losses = [t for t in trades if float(t.get("realized_pnl", 0) or 0) < 0]
            if losses:
                self.log(f"Found {len(losses)} losing trades", True)

                # Check if loss_analysis field is populated
                with_analysis = [t for t in losses if t.get("loss_analysis")]
                pct = (len(with_analysis) / len(losses) * 100) if losses else 0
                self.log(f"Losses with loss_analysis populated", pct > 0, f"{len(with_analysis)}/{len(losses)} ({pct:.0f}%)")

                # Check MFE/MAE fields
                with_mfe = [t for t in losses if t.get("mfe_points") is not None]
                pct = (len(with_mfe) / len(losses) * 100) if losses else 0
                self.log(f"Losses with mfe_points populated", pct > 0, f"{len(with_mfe)}/{len(losses)} ({pct:.0f}%)")

                with_mae = [t for t in losses if t.get("mae_points") is not None]
                pct = (len(with_mae) / len(losses) * 100) if losses else 0
                self.log(f"Losses with mae_points populated", pct > 0, f"{len(with_mae)}/{len(losses)} ({pct:.0f}%)")

            else:
                self.log("Has losing trades for analysis", False, "No losses found - all wins!")

            # Check close_reason distribution
            reasons = {}
            for t in trades:
                reason = t.get("close_reason", "UNKNOWN")
                reasons[reason] = reasons.get(reason, 0) + 1

            self.log("Close reasons tracked", True, f"Found {len(reasons)} distinct reasons")
            for reason, count in sorted(reasons.items(), key=lambda x: -x[1])[:5]:
                print(f"       - {reason}: {count}")

        else:
            self.log("Closed trades endpoint works", False)

    # ==================================================================
    # Run All Tests
    # ==================================================================

    def run_all(self):
        """Run complete test suite"""
        print("\n" + "=" * 70)
        print("HERACLES IMPLEMENTATION VERIFICATION AUDIT")
        print(f"API URL: {self.api_url}")
        print(f"Time: {datetime.now().isoformat()}")
        print("=" * 70)

        # Run all test phases
        self.test_api_endpoints()
        self.test_data_contracts()
        self.test_feature_implementation()
        self.test_max_loss_rule()
        self.test_loss_analysis()

        # Summary
        print("\n" + "=" * 70)
        print("AUDIT SUMMARY")
        print("=" * 70)
        total = self.passed + self.failed
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed} ({self.passed/total*100:.1f}%)")
        print(f"Failed: {self.failed} ({self.failed/total*100:.1f}%)")

        if self.failed == 0:
            print("\n✅ ALL TESTS PASSED - Implementation verified")
        else:
            print(f"\n❌ {self.failed} FAILURES - Review and fix before deployment")

            # List failures
            print("\nFailed Tests:")
            for r in self.results:
                if not r["passed"]:
                    print(f"  - {r['test']}: {r['details']}")

        print("=" * 70)

        return 0 if self.failed == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HERACLES Implementation Audit")
    parser.add_argument("--api-url", type=str, default="http://localhost:8000",
                        help="API base URL (e.g., https://your-app.render.com)")
    args = parser.parse_args()

    tester = HERACLESAuditTester(api_url=args.api_url)
    exit_code = tester.run_all()
    sys.exit(exit_code)
