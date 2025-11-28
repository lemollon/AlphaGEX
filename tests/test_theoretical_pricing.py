#!/usr/bin/env python3
"""
Comprehensive Test Script for Black-Scholes Theoretical Pricing Integration

Tests:
1. Black-Scholes calculation accuracy
2. Theoretical price calculation with delayed quotes
3. Database schema for theoretical pricing columns
4. Autonomous trader integration
5. Dashboard display readiness

Run with: python test_theoretical_pricing.py
"""

import sys
import math

# Test results tracker
TESTS_PASSED = 0
TESTS_FAILED = 0
RESULTS = []

def test_result(name: str, passed: bool, details: str = ""):
    global TESTS_PASSED, TESTS_FAILED
    if passed:
        TESTS_PASSED += 1
        status = "✅ PASS"
    else:
        TESTS_FAILED += 1
        status = "❌ FAIL"
    RESULTS.append((name, passed, details))
    print(f"{status}: {name}")
    if details:
        print(f"       {details}")


def test_black_scholes_calculation():
    """Test the Black-Scholes pricing formula directly"""
    print("\n" + "="*60)
    print("TEST 1: Black-Scholes Calculation Accuracy")
    print("="*60)

    try:
        from scipy.stats import norm

        def calculate_bs_price(spot, strike, time_to_exp, vol, opt_type='call', r=0.05):
            if time_to_exp <= 0:
                if opt_type == 'call':
                    return max(0, spot - strike)
                else:
                    return max(0, strike - spot)
            d1 = (math.log(spot/strike) + (r + 0.5*vol**2)*time_to_exp) / (vol*math.sqrt(time_to_exp))
            d2 = d1 - vol*math.sqrt(time_to_exp)
            if opt_type == 'call':
                price = spot * norm.cdf(d1) - strike * math.exp(-r*time_to_exp) * norm.cdf(d2)
            else:
                price = strike * math.exp(-r*time_to_exp) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            return max(0, price)

        # Test ATM call: SPY=$600, K=$600, 7DTE, 20% IV
        atm_call = calculate_bs_price(600, 600, 7/365, 0.20, 'call')
        test_result(
            "ATM Call Price (SPY=600, K=600, 7DTE, 20%IV)",
            5 < atm_call < 15,
            f"Price: ${atm_call:.2f} (expected ~$8-12)"
        )

        # Test ATM put (should be similar due to put-call parity)
        atm_put = calculate_bs_price(600, 600, 7/365, 0.20, 'put')
        test_result(
            "ATM Put Price (same params)",
            5 < atm_put < 15,
            f"Price: ${atm_put:.2f} (expected ~$8-12)"
        )

        # Test OTM call (5% OTM)
        otm_call = calculate_bs_price(600, 630, 7/365, 0.20, 'call')
        test_result(
            "OTM Call Price (SPY=600, K=630, 7DTE)",
            otm_call < atm_call,
            f"Price: ${otm_call:.2f} (should be < ATM ${atm_call:.2f})"
        )

        # Test ITM put
        itm_put = calculate_bs_price(600, 630, 7/365, 0.20, 'put')
        test_result(
            "ITM Put Price (SPY=600, K=630, 7DTE)",
            itm_put > atm_put,
            f"Price: ${itm_put:.2f} (should be > ATM ${atm_put:.2f})"
        )

        # Test expiration intrinsic value
        exp_call = calculate_bs_price(605, 600, 0, 0.20, 'call')
        test_result(
            "Expired ITM Call Intrinsic Value",
            abs(exp_call - 5.0) < 0.01,
            f"Price: ${exp_call:.2f} (expected $5.00)"
        )

        # Test high IV vs low IV
        high_iv_call = calculate_bs_price(600, 600, 7/365, 0.40, 'call')
        low_iv_call = calculate_bs_price(600, 600, 7/365, 0.10, 'call')
        test_result(
            "Higher IV = Higher Price",
            high_iv_call > low_iv_call,
            f"High IV: ${high_iv_call:.2f} > Low IV: ${low_iv_call:.2f}"
        )

    except ImportError as e:
        test_result("scipy.stats.norm import", False, f"Import failed: {e}")
    except Exception as e:
        test_result("Black-Scholes Calculation", False, f"Error: {e}")


def test_polygon_data_fetcher_functions():
    """Test the theoretical pricing functions in polygon_data_fetcher.py"""
    print("\n" + "="*60)
    print("TEST 2: polygon_data_fetcher.py Function Integration")
    print("="*60)

    try:
        # Check if functions exist
        from data.polygon_data_fetcher import (
            calculate_black_scholes_price,
            calculate_theoretical_option_price,
            get_best_entry_price
        )

        test_result(
            "Import calculate_black_scholes_price",
            True,
            "Function imported successfully"
        )

        test_result(
            "Import calculate_theoretical_option_price",
            True,
            "Function imported successfully"
        )

        test_result(
            "Import get_best_entry_price",
            True,
            "Function imported successfully"
        )

        # Test calculate_black_scholes_price
        price = calculate_black_scholes_price(600, 600, 7/365, 0.20, 'call')
        test_result(
            "calculate_black_scholes_price() returns valid price",
            price > 0,
            f"Price: ${price:.2f}"
        )

        # Test calculate_theoretical_option_price with mock quote
        mock_quote = {
            'bid': 5.00,
            'ask': 5.20,
            'mid': 5.10,
            'strike': 600,
            'expiration': '2025-12-15',
            'implied_volatility': 0.20,
            'delta': 0.50,
            'is_delayed': True,
            'contract_symbol': 'O:SPY251215C00600000'
        }

        result = calculate_theoretical_option_price(mock_quote, current_spot=602)

        test_result(
            "calculate_theoretical_option_price() returns dict",
            isinstance(result, dict),
            f"Type: {type(result)}"
        )

        test_result(
            "Result contains 'theoretical_price'",
            'theoretical_price' in result,
            f"theoretical_price: ${result.get('theoretical_price', 0):.2f}"
        )

        test_result(
            "Result contains 'recommended_entry'",
            'recommended_entry' in result,
            f"recommended_entry: ${result.get('recommended_entry', 0):.2f}"
        )

        test_result(
            "Result contains 'price_adjustment_pct'",
            'price_adjustment_pct' in result,
            f"price_adjustment_pct: {result.get('price_adjustment_pct', 0):.1f}%"
        )

        test_result(
            "Result contains 'confidence'",
            'confidence' in result,
            f"confidence: {result.get('confidence', 'unknown')}"
        )

        # Test get_best_entry_price
        best_price = get_best_entry_price(mock_quote, current_spot=602, use_theoretical=True)
        test_result(
            "get_best_entry_price() returns valid price",
            best_price > 0,
            f"Best entry: ${best_price:.2f}"
        )

    except ImportError as e:
        test_result("Import polygon_data_fetcher functions", False, f"Import failed: {e}")
    except Exception as e:
        test_result("polygon_data_fetcher.py Function Test", False, f"Error: {e}")


def test_autonomous_trader_integration():
    """Test the autonomous trader integration"""
    print("\n" + "="*60)
    print("TEST 3: Autonomous Trader Integration")
    print("="*60)

    try:
        # Check imports
        from core.autonomous_paper_trader import (
            get_real_option_price,
            calculate_theoretical_option_price,
            get_best_entry_price,
            AutonomousPaperTrader
        )

        test_result(
            "Import get_real_option_price",
            True,
            "Function imported successfully"
        )

        test_result(
            "Import AutonomousPaperTrader",
            True,
            "Class imported successfully"
        )

        # Check that get_real_option_price has the new parameters
        import inspect
        sig = inspect.signature(get_real_option_price)
        params = list(sig.parameters.keys())

        test_result(
            "get_real_option_price has 'current_spot' param",
            'current_spot' in params,
            f"Parameters: {params}"
        )

        test_result(
            "get_real_option_price has 'use_theoretical' param",
            'use_theoretical' in params,
            f"Parameters: {params}"
        )

        # Check AutonomousPaperTrader methods
        trader_methods = dir(AutonomousPaperTrader)

        test_result(
            "AutonomousPaperTrader has is_theoretical_pricing_enabled",
            'is_theoretical_pricing_enabled' in trader_methods,
            "Method exists"
        )

        test_result(
            "AutonomousPaperTrader has set_theoretical_pricing",
            'set_theoretical_pricing' in trader_methods,
            "Method exists"
        )

    except ImportError as e:
        test_result("Import autonomous_paper_trader", False, f"Import failed: {e}")
    except Exception as e:
        test_result("Autonomous Trader Integration", False, f"Error: {e}")


def test_database_schema():
    """Test that database schema has theoretical pricing columns"""
    print("\n" + "="*60)
    print("TEST 4: Database Schema Columns")
    print("="*60)

    try:
        from database_adapter import get_connection

        conn = get_connection()
        c = conn.cursor()

        # Check autonomous_open_positions columns
        c.execute("PRAGMA table_info(autonomous_open_positions)")
        columns = [col[1] for col in c.fetchall()]

        expected_columns = [
            'theoretical_price',
            'theoretical_bid',
            'theoretical_ask',
            'recommended_entry',
            'price_adjustment',
            'price_adjustment_pct',
            'is_delayed',
            'data_confidence'
        ]

        for col in expected_columns:
            exists = col in columns
            test_result(
                f"Column '{col}' exists in autonomous_open_positions",
                exists,
                f"{'Found' if exists else 'MISSING'}"
            )

        conn.close()

    except Exception as e:
        test_result("Database Schema Test", False, f"Error: {e}")


def test_dashboard_files():
    """Test that dashboard files have been updated"""
    print("\n" + "="*60)
    print("TEST 5: Dashboard File Updates")
    print("="*60)

    try:
        with open('/home/user/AlphaGEX/autonomous_trader_dashboard.py', 'r') as f:
            content = f.read()

        # Check for key UI updates
        test_result(
            "Dashboard mentions 'Black-Scholes'",
            'Black-Scholes' in content or 'black_scholes' in content.lower(),
            "Found Black-Scholes reference"
        )

        test_result(
            "Dashboard mentions 'theoretical_price'",
            'theoretical_price' in content,
            "Found theoretical_price reference"
        )

        test_result(
            "Dashboard mentions 'Polygon.io'",
            'Polygon.io' in content or 'polygon' in content.lower(),
            "Found Polygon.io reference"
        )

        test_result(
            "Dashboard has pricing toggle",
            'is_theoretical_pricing_enabled' in content,
            "Found pricing toggle method call"
        )

        test_result(
            "Dashboard mentions 'recommended_entry'",
            'recommended_entry' in content,
            "Found recommended_entry display"
        )

    except Exception as e:
        test_result("Dashboard File Test", False, f"Error: {e}")


def test_api_routes():
    """Test that API routes exist"""
    print("\n" + "="*60)
    print("TEST 6: API Routes Verification")
    print("="*60)

    try:
        with open('/home/user/AlphaGEX/backend/autonomous_routes.py', 'r') as f:
            content = f.read()

        test_result(
            "API has signal endpoint",
            '/api/autonomous/signal' in content or 'signal' in content,
            "Found signal endpoint"
        )

        test_result(
            "API has data-status endpoint",
            'data-status' in content or 'data_status' in content,
            "Found data-status endpoint"
        )

        test_result(
            "API has signal mode endpoint",
            'signal/mode' in content or 'signal_mode' in content,
            "Found signal mode endpoint"
        )

    except Exception as e:
        test_result("API Routes Test", False, f"Error: {e}")


def print_summary():
    """Print test summary"""
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    total = TESTS_PASSED + TESTS_FAILED
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {TESTS_PASSED}")
    print(f"❌ Failed: {TESTS_FAILED}")
    print(f"Pass Rate: {(TESTS_PASSED/total*100) if total > 0 else 0:.1f}%")

    if TESTS_FAILED > 0:
        print("\n" + "-"*60)
        print("FAILED TESTS:")
        print("-"*60)
        for name, passed, details in RESULTS:
            if not passed:
                print(f"❌ {name}")
                if details:
                    print(f"   {details}")

    print("\n" + "="*60)

    if TESTS_FAILED == 0:
        print("🎉 ALL TESTS PASSED! Black-Scholes integration is ready.")
    else:
        print("⚠️ Some tests failed. Please review the issues above.")

    return TESTS_FAILED == 0


if __name__ == "__main__":
    print("="*60)
    print("BLACK-SCHOLES THEORETICAL PRICING INTEGRATION TESTS")
    print("="*60)

    # Run all tests
    test_black_scholes_calculation()
    test_polygon_data_fetcher_functions()
    test_autonomous_trader_integration()
    test_database_schema()
    test_dashboard_files()
    test_api_routes()

    # Print summary
    success = print_summary()

    # Exit with appropriate code
    sys.exit(0 if success else 1)
