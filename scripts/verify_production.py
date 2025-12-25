#!/usr/bin/env python3
"""
Production Verification Script for AlphaGEX

Usage:
    python scripts/verify_production.py                    # Test against localhost:8000
    python scripts/verify_production.py https://api.example.com  # Test against production

This script verifies:
1. Health endpoint
2. Database connectivity
3. GEX data pipeline
4. Trading system status
5. All critical API routes
"""

import sys
import os
import json
import time
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("❌ requests library not installed. Run: pip install requests")
    sys.exit(1)


class ProductionVerifier:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.results = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0

    def check(self, name: str, endpoint: str, expected_keys: list = None,
              expected_status: int = 200, timeout: int = 10):
        """Run a single verification check."""
        url = f"{self.base_url}{endpoint}"

        try:
            start = time.time()
            response = requests.get(url, timeout=timeout)
            elapsed = (time.time() - start) * 1000  # ms

            # Check status code
            if response.status_code != expected_status:
                self._fail(name, f"Expected status {expected_status}, got {response.status_code}")
                return False

            # Check response time
            if elapsed > 5000:
                self._warn(name, f"Slow response: {elapsed:.0f}ms")

            # Check expected keys in JSON response
            if expected_keys:
                try:
                    data = response.json()
                    missing = [k for k in expected_keys if k not in data]
                    if missing:
                        self._fail(name, f"Missing keys: {missing}")
                        return False
                except json.JSONDecodeError:
                    self._fail(name, "Invalid JSON response")
                    return False

            self._pass(name, f"{elapsed:.0f}ms")
            return True

        except requests.Timeout:
            self._fail(name, f"Timeout after {timeout}s")
            return False
        except requests.ConnectionError as e:
            self._fail(name, f"Connection failed: {e}")
            return False
        except Exception as e:
            self._fail(name, f"Error: {e}")
            return False

    def _pass(self, name: str, details: str = ""):
        self.passed += 1
        detail_str = f" ({details})" if details else ""
        print(f"  ✅ {name}{detail_str}")
        self.results.append({"name": name, "status": "pass", "details": details})

    def _fail(self, name: str, details: str = ""):
        self.failed += 1
        print(f"  ❌ {name}: {details}")
        self.results.append({"name": name, "status": "fail", "details": details})

    def _warn(self, name: str, details: str = ""):
        self.warnings += 1
        print(f"  ⚠️  {name}: {details}")
        self.results.append({"name": name, "status": "warn", "details": details})

    def run_all_checks(self):
        """Run all production verification checks."""
        print(f"\n{'='*60}")
        print(f"  ALPHAGEX PRODUCTION VERIFICATION")
        print(f"  Target: {self.base_url}")
        print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        # 1. Health Check
        print("📡 HEALTH & CONNECTIVITY")
        self.check("Health endpoint", "/health", ["status"])
        self.check("Database connection", "/health", ["database"])
        print()

        # 2. GEX Data Pipeline
        print("📊 GEX DATA PIPELINE")
        self.check("GEX data (SPY)", "/api/gex/SPY", ["symbol", "spot_price"])
        self.check("Regime classification", "/api/gex/SPY/regime", ["regime"])
        self.check("VIX data", "/api/vix/current", ["vix"])
        print()

        # 3. Trading System
        print("🤖 TRADING SYSTEM")
        self.check("Trader status", "/api/trader/status", ["status"])
        self.check("Open positions", "/api/trader/positions")
        self.check("Strategy stats", "/api/backtests/results")
        print()

        # 4. Bot Systems
        print("🦾 BOT SYSTEMS")
        self.check("ARES status", "/api/ares/status")
        self.check("ATHENA status", "/api/athena/status")
        self.check("APOLLO status", "/api/apollo/status")
        self.check("PROMETHEUS status", "/api/prometheus/status")
        print()

        # 5. Core API Routes
        print("🔌 CORE API ROUTES")
        self.check("Gamma data", "/api/gamma/SPY")
        self.check("Options chain", "/api/gex/SPY/chain")
        self.check("Price history", "/api/price-history?symbol=SPY&days=5")
        print()

        # 6. Database Operations
        print("🗄️ DATABASE OPERATIONS")
        self.check("Database stats", "/api/database/stats")
        self.check("Decision logs", "/api/logs/decisions?limit=1")
        print()

        # 7. SPX Wheel System
        print("🎡 SPX WHEEL SYSTEM")
        self.check("SPX wheel status", "/api/spx/wheel/status")
        self.check("SPX positions", "/api/spx/wheel/positions")
        print()

        # Summary
        self._print_summary()

        return self.failed == 0

    def _print_summary(self):
        """Print verification summary."""
        total = self.passed + self.failed

        print(f"\n{'='*60}")
        print(f"  VERIFICATION SUMMARY")
        print(f"{'='*60}")
        print(f"  ✅ Passed:   {self.passed}/{total}")
        print(f"  ❌ Failed:   {self.failed}/{total}")
        print(f"  ⚠️  Warnings: {self.warnings}")
        print()

        if self.failed == 0:
            print("  🎉 ALL CHECKS PASSED - SYSTEM IS PRODUCTION READY!")
        else:
            print("  🚨 SOME CHECKS FAILED - REVIEW BEFORE GOING LIVE")
            print("\n  Failed checks:")
            for r in self.results:
                if r["status"] == "fail":
                    print(f"    - {r['name']}: {r['details']}")

        print(f"{'='*60}\n")


def check_env_vars():
    """Check if required environment variables are set."""
    print("\n🔐 ENVIRONMENT VARIABLES CHECK")
    print("-" * 40)

    required = [
        ("DATABASE_URL", "PostgreSQL connection"),
        ("TRADIER_API_KEY", "Tradier API"),
        ("POLYGON_API_KEY", "Polygon.io API"),
        ("TRADING_VOL_API_KEY", "Trading Volatility API"),
    ]

    optional = [
        ("ANTHROPIC_API_KEY", "Claude AI"),
        ("TRADIER_ACCOUNT_ID", "Live trading"),
        ("TRADIER_SANDBOX", "Sandbox mode"),
    ]

    all_set = True

    print("\nRequired:")
    for var, desc in required:
        value = os.getenv(var)
        if value:
            # Show first 4 chars only for security
            masked = value[:4] + "..." if len(value) > 4 else "****"
            print(f"  ✅ {var}: {masked} ({desc})")
        else:
            print(f"  ❌ {var}: NOT SET ({desc})")
            all_set = False

    print("\nOptional:")
    for var, desc in optional:
        value = os.getenv(var)
        if value:
            masked = value[:4] + "..." if len(value) > 4 else "****"
            print(f"  ✅ {var}: {masked} ({desc})")
        else:
            print(f"  ⚪ {var}: not set ({desc})")

    print()
    return all_set


def main():
    # Determine target URL
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    else:
        base_url = os.getenv("API_URL", "http://localhost:8000")

    # Check environment variables first
    env_ok = check_env_vars()

    if not env_ok:
        print("⚠️  Some required environment variables are missing!")
        print("   Set them before running production.\n")

    # Run verification
    verifier = ProductionVerifier(base_url)
    success = verifier.run_all_checks()

    # Exit code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
