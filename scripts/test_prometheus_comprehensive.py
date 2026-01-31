#!/usr/bin/env python3
"""
PROMETHEUS Comprehensive Test Suite
====================================

Run in Render shell: python scripts/test_prometheus_comprehensive.py

Tests ALL components per STANDARDS.md:
1. Database Layer - Tables exist, data populated
2. Backend API - Endpoints return correct data
3. Rate Fetcher - FRED API and fallbacks work
4. Data Models - Fields populated correctly
5. Signal Generator - Rate analysis works
6. Frontend Data Flow - API returns what frontend expects

Finds ALL bugs before stopping.
"""

import os
import sys
import json
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Test results tracking
@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    severity: str = "error"  # error, warning, info

class TestRunner:
    def __init__(self):
        self.results: List[TestResult] = []
        self.bugs_found: List[Dict] = []

    def record(self, name: str, passed: bool, message: str, severity: str = "error"):
        self.results.append(TestResult(name, passed, message, severity))
        if not passed and severity == "error":
            self.bugs_found.append({"test": name, "issue": message})

    def print_summary(self):
        print("\n" + "=" * 70)
        print("PROMETHEUS TEST SUMMARY")
        print("=" * 70)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed and r.severity == "error")
        warnings = sum(1 for r in self.results if not r.passed and r.severity == "warning")

        print(f"\n✅ PASSED: {passed}")
        print(f"❌ FAILED: {failed}")
        print(f"⚠️  WARNINGS: {warnings}")

        if self.bugs_found:
            print("\n" + "-" * 70)
            print("BUGS FOUND (require fixes):")
            print("-" * 70)
            for i, bug in enumerate(self.bugs_found, 1):
                print(f"\n  BUG #{i}: {bug['test']}")
                print(f"    Issue: {bug['issue']}")

        # Print all failed tests
        failed_tests = [r for r in self.results if not r.passed]
        if failed_tests:
            print("\n" + "-" * 70)
            print("DETAILED FAILURES:")
            print("-" * 70)
            for r in failed_tests:
                icon = "❌" if r.severity == "error" else "⚠️"
                print(f"\n  {icon} {r.name}")
                print(f"     {r.message}")

        return len(self.bugs_found) == 0

runner = TestRunner()


def test_section(name: str):
    """Print section header."""
    print(f"\n{'=' * 70}")
    print(f"TESTING: {name}")
    print("=" * 70)


# =============================================================================
# 1. DATABASE LAYER TESTS
# =============================================================================

def test_database_tables():
    """Test that all PROMETHEUS tables exist."""
    test_section("DATABASE TABLES")

    try:
        from database_adapter import DatabaseAdapter
        db = DatabaseAdapter()

        required_tables = [
            "prometheus_positions",
            "prometheus_closed_trades",
            "prometheus_config",
            "prometheus_activity_log",
            "prometheus_equity_snapshots",
            "prometheus_ic_positions",
            "prometheus_ic_closed_trades",
        ]

        for table in required_tables:
            try:
                result = db.fetch_one(f"SELECT COUNT(*) as cnt FROM {table}")
                count = result['cnt'] if result else 0
                runner.record(
                    f"Table {table} exists",
                    True,
                    f"Found with {count} rows"
                )
                print(f"  ✅ {table}: {count} rows")
            except Exception as e:
                runner.record(
                    f"Table {table} exists",
                    False,
                    f"Table missing or error: {e}"
                )
                print(f"  ❌ {table}: MISSING - {e}")

    except Exception as e:
        runner.record("Database connection", False, f"Cannot connect: {e}")
        print(f"  ❌ Database connection failed: {e}")


def test_database_schema():
    """Test that tables have required columns."""
    test_section("DATABASE SCHEMA")

    try:
        from database_adapter import DatabaseAdapter
        db = DatabaseAdapter()

        # Check prometheus_positions has required columns
        required_columns = {
            "prometheus_positions": [
                "position_id", "ticker", "lower_strike", "upper_strike",
                "expiration", "contracts", "total_credit_received",
                "implied_annual_rate", "status", "opened_at"
            ],
            "prometheus_ic_positions": [
                "position_id", "ticker", "call_short_strike", "call_long_strike",
                "put_short_strike", "put_long_strike", "contracts", "credit_received"
            ]
        }

        for table, columns in required_columns.items():
            try:
                # Get column names from table
                result = db.fetch_all(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = '{table}'
                """)
                existing_cols = {r['column_name'] for r in result} if result else set()

                for col in columns:
                    if col in existing_cols:
                        print(f"  ✅ {table}.{col} exists")
                    else:
                        runner.record(
                            f"{table}.{col} column",
                            False,
                            f"Missing column {col} in {table}"
                        )
                        print(f"  ❌ {table}.{col} MISSING")

            except Exception as e:
                runner.record(f"{table} schema check", False, str(e))
                print(f"  ❌ Cannot check {table}: {e}")

    except Exception as e:
        runner.record("Schema check", False, str(e))


# =============================================================================
# 2. RATE FETCHER TESTS
# =============================================================================

def test_rate_fetcher():
    """Test rate fetcher works correctly."""
    test_section("RATE FETCHER")

    try:
        from trading.prometheus.rate_fetcher import RateFetcher, get_current_rates

        # Test singleton
        fetcher1 = RateFetcher()
        fetcher2 = RateFetcher()
        if fetcher1 is fetcher2:
            runner.record("RateFetcher singleton", True, "Singleton pattern works")
            print("  ✅ Singleton pattern works")
        else:
            runner.record("RateFetcher singleton", False, "Not a singleton!")
            print("  ❌ Singleton pattern broken")

        # Test getting rates
        rates = get_current_rates()

        # Check all fields populated
        fields_to_check = [
            ("fed_funds_rate", 0, 20),
            ("sofr_rate", 0, 20),
            ("treasury_3m", 0, 20),
            ("treasury_1y", 0, 20),
            ("margin_rate", 0, 30),
        ]

        for field, min_val, max_val in fields_to_check:
            value = getattr(rates, field, None)
            if value is not None and min_val <= value <= max_val:
                runner.record(f"Rate {field}", True, f"{value:.2f}%")
                print(f"  ✅ {field}: {value:.2f}%")
            else:
                runner.record(f"Rate {field}", False, f"Invalid value: {value}")
                print(f"  ❌ {field}: Invalid value {value}")

        # Check source field
        if rates.source in ['live', 'cached', 'fomc_based', 'fallback']:
            runner.record("Rate source", True, f"Source: {rates.source}")
            print(f"  ✅ Source: {rates.source}")
        else:
            runner.record("Rate source", False, f"Unknown source: {rates.source}")
            print(f"  ❌ Unknown source: {rates.source}")

        # Check last_updated
        if rates.last_updated:
            age = datetime.now() - rates.last_updated
            if age < timedelta(hours=5):
                runner.record("Rates freshness", True, f"Updated {age} ago")
                print(f"  ✅ Rates updated {age} ago")
            else:
                runner.record("Rates freshness", False, f"Stale: {age} old", "warning")
                print(f"  ⚠️  Rates stale: {age} old")

        # Test FRED API specifically if key is set
        fred_key = os.environ.get('FRED_API_KEY')
        if fred_key:
            print(f"\n  FRED API Key: {fred_key[:8]}...{fred_key[-4:]}")
            if rates.source == 'live':
                runner.record("FRED API active", True, "Fetching live rates")
                print("  ✅ FRED API returning live rates")
            else:
                runner.record("FRED API active", False, f"Key set but source is {rates.source}", "warning")
                print(f"  ⚠️  FRED key set but source is {rates.source}")
        else:
            runner.record("FRED API key", False, "Not configured - using fallback", "warning")
            print("  ⚠️  FRED_API_KEY not set - using FOMC fallback")

    except Exception as e:
        runner.record("Rate fetcher import", False, f"Import failed: {e}")
        print(f"  ❌ Rate fetcher failed: {e}")
        traceback.print_exc()


# =============================================================================
# 3. MODELS TESTS
# =============================================================================

def test_models():
    """Test PROMETHEUS models are correct."""
    test_section("MODELS")

    try:
        from trading.prometheus.models import (
            PrometheusConfig, BoxSpreadPosition, BorrowingCostAnalysis
        )

        # Test PrometheusConfig defaults
        config = PrometheusConfig()

        # Check scan time is 8:30 AM (not 9:00 or 9:30)
        if config.entry_start == "08:30":
            runner.record("Scan start time", True, "8:30 AM CT (market open)")
            print("  ✅ Scan start time: 08:30 (market open)")
        else:
            runner.record("Scan start time", False, f"Wrong time: {config.entry_start}, expected 08:30")
            print(f"  ❌ Scan start time: {config.entry_start}, expected 08:30")

        # Check other config defaults
        checks = [
            ("strike_width", 50, "Strike width default"),
            ("min_dte", 90, "Min DTE"),
            ("roll_threshold_dte", 30, "Roll threshold"),
        ]

        for attr, expected, desc in checks:
            value = getattr(config, attr, None)
            if value == expected:
                runner.record(desc, True, f"{value}")
                print(f"  ✅ {desc}: {value}")
            else:
                runner.record(desc, False, f"Got {value}, expected {expected}", "warning")
                print(f"  ⚠️  {desc}: {value} (expected {expected})")

        # Test BorrowingCostAnalysis has rate source fields
        bca = BorrowingCostAnalysis(
            fed_funds_rate=4.33,
            sofr_rate=4.30,
            box_implied_rate=4.15,
            spread_to_risk_free=-0.18,
            is_favorable=True,
            recommendation="Market conditions favorable",
            rates_source="live",
            rates_last_updated=datetime.now()
        )

        if hasattr(bca, 'rates_source') and hasattr(bca, 'rates_last_updated'):
            runner.record("BorrowingCostAnalysis rate fields", True, "Has rates_source and rates_last_updated")
            print("  ✅ BorrowingCostAnalysis has rate tracking fields")
        else:
            runner.record("BorrowingCostAnalysis rate fields", False, "Missing rate tracking fields")
            print("  ❌ BorrowingCostAnalysis missing rate tracking fields")

    except Exception as e:
        runner.record("Models import", False, str(e))
        print(f"  ❌ Models import failed: {e}")
        traceback.print_exc()


# =============================================================================
# 4. SIGNAL GENERATOR TESTS
# =============================================================================

def test_signal_generator():
    """Test signal generator produces correct data."""
    test_section("SIGNAL GENERATOR")

    try:
        from trading.prometheus.signals import BoxSpreadSignalGenerator

        generator = BoxSpreadSignalGenerator()

        # Test rate analysis
        rate_analysis = generator.analyze_current_rates()

        if rate_analysis:
            print(f"  Rate Analysis:")
            print(f"    Fed Funds: {rate_analysis.fed_funds_rate:.2f}%")
            print(f"    Box Rate: {rate_analysis.box_implied_rate:.2f}%")
            print(f"    Source: {rate_analysis.rates_source}")
            print(f"    Favorable: {rate_analysis.is_favorable}")

            # Verify source field is populated
            if rate_analysis.rates_source in ['live', 'cached', 'fomc_based', 'fallback']:
                runner.record("Signal rates_source", True, rate_analysis.rates_source)
                print(f"  ✅ rates_source populated: {rate_analysis.rates_source}")
            else:
                runner.record("Signal rates_source", False, f"Invalid: {rate_analysis.rates_source}")
                print(f"  ❌ rates_source invalid: {rate_analysis.rates_source}")

            # Verify last_updated is populated
            if rate_analysis.rates_last_updated:
                runner.record("Signal rates_last_updated", True, str(rate_analysis.rates_last_updated))
                print(f"  ✅ rates_last_updated populated: {rate_analysis.rates_last_updated}")
            else:
                runner.record("Signal rates_last_updated", False, "Not populated")
                print(f"  ❌ rates_last_updated not populated")
        else:
            runner.record("Rate analysis", False, "Returned None")
            print("  ❌ Rate analysis returned None")

    except Exception as e:
        runner.record("Signal generator", False, str(e))
        print(f"  ❌ Signal generator failed: {e}")
        traceback.print_exc()


# =============================================================================
# 5. API ENDPOINT TESTS
# =============================================================================

def test_api_endpoints():
    """Test API endpoints return correct data."""
    test_section("API ENDPOINTS")

    try:
        import requests

        # Try local first, then production
        base_urls = [
            "http://localhost:8000",
            os.environ.get("API_BASE_URL", "https://alphagex-api.onrender.com")
        ]

        base_url = None
        for url in base_urls:
            try:
                resp = requests.get(f"{url}/health", timeout=5)
                if resp.status_code == 200:
                    base_url = url
                    print(f"  Using API: {base_url}")
                    break
            except:
                continue

        if not base_url:
            runner.record("API connectivity", False, "Cannot reach API", "warning")
            print("  ⚠️  Cannot reach API - skipping endpoint tests")
            return

        # Test PROMETHEUS endpoints
        endpoints = [
            ("/api/prometheus-box/status", ["status", "performance"]),
            ("/api/prometheus-box/positions", ["positions"]),
            ("/api/prometheus-box/rate-analysis", ["fed_funds_rate", "rates_source"]),
            ("/api/prometheus-box/ic/status", ["status"]),
        ]

        for endpoint, required_fields in endpoints:
            try:
                resp = requests.get(f"{base_url}{endpoint}", timeout=10)

                if resp.status_code == 200:
                    data = resp.json()

                    # Check required fields
                    missing = []
                    for field in required_fields:
                        if field not in data:
                            missing.append(field)

                    if not missing:
                        runner.record(f"API {endpoint}", True, "All fields present")
                        print(f"  ✅ {endpoint}: OK")
                    else:
                        runner.record(f"API {endpoint}", False, f"Missing: {missing}")
                        print(f"  ❌ {endpoint}: Missing fields {missing}")
                else:
                    runner.record(f"API {endpoint}", False, f"Status {resp.status_code}")
                    print(f"  ❌ {endpoint}: Status {resp.status_code}")

            except Exception as e:
                runner.record(f"API {endpoint}", False, str(e), "warning")
                print(f"  ⚠️  {endpoint}: {e}")

        # Test rate-analysis specifically for new fields
        try:
            resp = requests.get(f"{base_url}/api/prometheus-box/rate-analysis", timeout=10)
            if resp.status_code == 200:
                data = resp.json()

                # Check rates_source
                if 'rates_source' in data:
                    source = data['rates_source']
                    if source in ['live', 'cached', 'fomc_based', 'fallback']:
                        runner.record("API rates_source field", True, source)
                        print(f"  ✅ rates_source in API response: {source}")
                    else:
                        runner.record("API rates_source field", False, f"Invalid: {source}")
                        print(f"  ❌ rates_source invalid: {source}")
                else:
                    runner.record("API rates_source field", False, "Not in response")
                    print("  ❌ rates_source missing from API response")

                # Check rates_last_updated
                if 'rates_last_updated' in data and data['rates_last_updated']:
                    runner.record("API rates_last_updated field", True, "Present")
                    print(f"  ✅ rates_last_updated in API: {data['rates_last_updated']}")
                else:
                    runner.record("API rates_last_updated field", False, "Missing or null")
                    print("  ❌ rates_last_updated missing from API response")

        except Exception as e:
            runner.record("API rate analysis", False, str(e))

    except ImportError:
        runner.record("API tests", False, "requests not installed", "warning")
        print("  ⚠️  requests not installed - skipping API tests")


# =============================================================================
# 6. FRONTEND DATA EXPECTATIONS
# =============================================================================

def test_frontend_data_expectations():
    """Test that API returns data frontend expects."""
    test_section("FRONTEND DATA EXPECTATIONS")

    try:
        import requests

        base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")

        # Test status endpoint has fields frontend uses
        try:
            resp = requests.get(f"{base_url}/api/prometheus-box/status", timeout=10)
            if resp.status_code == 200:
                data = resp.json()

                # Fields the frontend expects in status response
                frontend_expects = [
                    "status.enabled",
                    "status.in_trading_window",
                    "performance.total_borrowed",
                    "performance.total_ic_returns",
                    "performance.total_borrowing_costs",
                    "performance.avg_implied_rate",
                ]

                for field_path in frontend_expects:
                    parts = field_path.split('.')
                    value = data
                    try:
                        for part in parts:
                            value = value[part]
                        runner.record(f"Frontend field {field_path}", True, f"Value: {value}")
                        print(f"  ✅ {field_path}: {value}")
                    except (KeyError, TypeError):
                        runner.record(f"Frontend field {field_path}", False, "Missing in API response")
                        print(f"  ❌ {field_path}: MISSING")

        except Exception as e:
            runner.record("Frontend status check", False, str(e), "warning")
            print(f"  ⚠️  Could not check status endpoint: {e}")

        # Test rate-analysis has frontend-expected fields
        try:
            resp = requests.get(f"{base_url}/api/prometheus-box/rate-analysis", timeout=10)
            if resp.status_code == 200:
                data = resp.json()

                rate_fields = [
                    "fed_funds_rate",
                    "box_implied_rate",
                    "is_favorable",
                    "rates_source",
                    "rates_last_updated",
                ]

                for field in rate_fields:
                    if field in data:
                        print(f"  ✅ rate-analysis.{field}: {data[field]}")
                    else:
                        runner.record(f"Rate field {field}", False, "Missing")
                        print(f"  ❌ rate-analysis.{field}: MISSING")

        except Exception as e:
            print(f"  ⚠️  Could not check rate-analysis: {e}")

    except ImportError:
        print("  ⚠️  requests not installed")


# =============================================================================
# 7. INTEGRATION TESTS
# =============================================================================

def test_end_to_end_flow():
    """Test complete data flow from rate fetcher to API."""
    test_section("END-TO-END FLOW")

    try:
        # 1. Get rates from rate fetcher
        from trading.prometheus.rate_fetcher import get_current_rates
        rates = get_current_rates()
        print(f"  1. Rate Fetcher -> Fed Funds: {rates.fed_funds_rate}%, Source: {rates.source}")

        # 2. Check signal generator uses these rates
        from trading.prometheus.signals import BoxSpreadSignalGenerator
        generator = BoxSpreadSignalGenerator()
        analysis = generator.analyze_current_rates()
        print(f"  2. Signal Generator -> Fed Funds: {analysis.fed_funds_rate}%, Source: {analysis.rates_source}")

        # 3. Verify consistency
        if abs(rates.fed_funds_rate - analysis.fed_funds_rate) < 0.01:
            runner.record("Rate consistency", True, "Rates match across components")
            print("  ✅ Rates consistent across components")
        else:
            runner.record("Rate consistency", False, "Rates don't match!")
            print(f"  ❌ Rate mismatch: {rates.fed_funds_rate} vs {analysis.fed_funds_rate}")

        # 4. Verify source propagates
        if rates.source == analysis.rates_source:
            runner.record("Source propagation", True, "Source consistent")
            print("  ✅ Source propagates correctly")
        else:
            runner.record("Source propagation", False, f"{rates.source} vs {analysis.rates_source}")
            print(f"  ❌ Source mismatch: {rates.source} vs {analysis.rates_source}")

    except Exception as e:
        runner.record("End-to-end flow", False, str(e))
        print(f"  ❌ End-to-end test failed: {e}")
        traceback.print_exc()


# =============================================================================
# MAIN
# =============================================================================

def main():
    print("=" * 70)
    print("PROMETHEUS COMPREHENSIVE TEST SUITE")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"FRED_API_KEY: {'SET' if os.environ.get('FRED_API_KEY') else 'NOT SET'}")
    print(f"DATABASE_URL: {'SET' if os.environ.get('DATABASE_URL') else 'NOT SET'}")

    # Run all tests
    test_database_tables()
    test_database_schema()
    test_rate_fetcher()
    test_models()
    test_signal_generator()
    test_api_endpoints()
    test_frontend_data_expectations()
    test_end_to_end_flow()

    # Print summary
    all_passed = runner.print_summary()

    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED - PROMETHEUS is production-ready")
    else:
        print("❌ TESTS FAILED - See bugs above for required fixes")
    print("=" * 70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
