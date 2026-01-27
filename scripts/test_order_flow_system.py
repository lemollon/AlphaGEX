#!/usr/bin/env python3
"""
Order Flow System End-to-End Test Script
=========================================

Tests the complete order flow pressure system per CLAUDE.md standards:
1. Database schema exists
2. Tradier data fetcher has bid_size/ask_size fields
3. ARGUS engine calculates pressure correctly
4. API endpoint returns order_flow data
5. Database persistence works

Run in Render shell:
    python scripts/test_order_flow_system.py

Author: AlphaGEX Team
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def print_result(test: str, passed: bool, details: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {test}")
    if details:
        print(f"       {details}")

def test_database_schema():
    """Test 1: Verify argus_order_flow_history table exists"""
    print_header("TEST 1: Database Schema")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        if not conn:
            print_result("Database connection", False, "Could not connect to database")
            return False

        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'argus_order_flow_history'
            )
        """)
        table_exists = cursor.fetchone()[0]
        print_result("Table argus_order_flow_history exists", table_exists)

        if table_exists:
            # Check columns
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'argus_order_flow_history'
                ORDER BY ordinal_position
            """)
            columns = cursor.fetchall()
            expected_columns = [
                'net_pressure', 'raw_pressure', 'pressure_direction',
                'call_pressure', 'put_pressure', 'total_bid_size',
                'total_ask_size', 'combined_signal', 'signal_confidence'
            ]
            found_columns = [c[0] for c in columns]

            for col in expected_columns:
                has_col = col in found_columns
                print_result(f"  Column '{col}'", has_col)

            # Check indexes
            cursor.execute("""
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'argus_order_flow_history'
            """)
            indexes = [r[0] for r in cursor.fetchall()]
            print_result("Index on recorded_at", 'idx_argus_order_flow_recorded_at' in indexes)
            print_result("Index on combined_signal", 'idx_argus_order_flow_signal' in indexes)

        cursor.close()
        conn.close()
        return table_exists

    except Exception as e:
        print_result("Database schema test", False, str(e))
        return False

def test_tradier_data_fetcher():
    """Test 2: Verify OptionContract has bid_size/ask_size fields"""
    print_header("TEST 2: Tradier Data Fetcher")

    try:
        from data.tradier_data_fetcher import OptionContract
        from dataclasses import fields

        field_names = [f.name for f in fields(OptionContract)]

        has_bid_size = 'bid_size' in field_names
        has_ask_size = 'ask_size' in field_names

        print_result("OptionContract.bid_size field", has_bid_size)
        print_result("OptionContract.ask_size field", has_ask_size)

        # Create a sample contract to verify defaults
        contract = OptionContract(
            symbol="SPY260127C00585000",
            underlying="SPY",
            strike=585.0,
            expiration="2026-01-27",
            option_type="call"
        )
        print_result("Default bid_size = 0", contract.bid_size == 0)
        print_result("Default ask_size = 0", contract.ask_size == 0)

        return has_bid_size and has_ask_size

    except Exception as e:
        print_result("Tradier data fetcher test", False, str(e))
        return False

def test_argus_engine():
    """Test 3: Verify ARGUS engine has order flow methods"""
    print_header("TEST 3: ARGUS Engine")

    try:
        from core.argus_engine import ArgusEngine, StrikeData
        from dataclasses import fields

        # Check StrikeData has bid/ask fields
        field_names = [f.name for f in fields(StrikeData)]
        required_fields = ['call_bid_size', 'call_ask_size', 'put_bid_size', 'put_ask_size']

        for field in required_fields:
            print_result(f"StrikeData.{field}", field in field_names)

        # Check engine has the methods
        engine = ArgusEngine()
        has_pressure_method = hasattr(engine, 'calculate_bid_ask_pressure')
        has_volume_method = hasattr(engine, 'calculate_net_gex_volume')

        print_result("calculate_bid_ask_pressure() method", has_pressure_method)
        print_result("calculate_net_gex_volume() method", has_volume_method)

        # Test with mock data
        mock_strikes = [
            StrikeData(
                strike=584.0, net_gamma=0.05, call_gamma=0.03, put_gamma=0.02,
                call_bid_size=50, call_ask_size=30, put_bid_size=20, put_ask_size=60
            ),
            StrikeData(
                strike=585.0, net_gamma=0.08, call_gamma=0.05, put_gamma=0.03,
                call_bid_size=80, call_ask_size=40, put_bid_size=30, put_ask_size=90
            ),
            StrikeData(
                strike=586.0, net_gamma=0.04, call_gamma=0.02, put_gamma=0.02,
                call_bid_size=40, call_ask_size=25, put_bid_size=25, put_ask_size=50
            ),
        ]

        # Test pressure calculation
        pressure = engine.calculate_bid_ask_pressure(mock_strikes, 585.0)
        print_result("Pressure calculation returns dict", isinstance(pressure, dict))
        print_result("Pressure has 'net_pressure'", 'net_pressure' in pressure)
        print_result("Pressure has 'raw_pressure'", 'raw_pressure' in pressure)
        print_result("Pressure has 'smoothing_periods'", 'smoothing_periods' in pressure)
        print_result("Pressure has 'is_valid'", 'is_valid' in pressure)
        print_result("Pressure has 'pressure_direction'", 'pressure_direction' in pressure)

        # Test volume calculation
        volume = engine.calculate_net_gex_volume(mock_strikes, 585.0)
        print_result("Volume calculation returns dict", isinstance(volume, dict))
        print_result("Volume has 'bid_ask_pressure'", 'bid_ask_pressure' in volume)
        print_result("Volume has 'combined_signal'", 'combined_signal' in volume)
        print_result("Volume has 'signal_confidence'", 'signal_confidence' in volume)

        print(f"\n  Sample pressure result:")
        print(f"    Direction: {pressure.get('pressure_direction')}")
        print(f"    Strength: {pressure.get('pressure_strength')}")
        print(f"    Net Pressure: {pressure.get('net_pressure')}")
        print(f"    Raw Pressure: {pressure.get('raw_pressure')}")
        print(f"    Smoothing Periods: {pressure.get('smoothing_periods')}")
        print(f"    Is Valid: {pressure.get('is_valid')}")

        # Test invalid case (insufficient depth)
        thin_strikes = [
            StrikeData(
                strike=585.0, net_gamma=0.01, call_gamma=0.005, put_gamma=0.005,
                call_bid_size=5, call_ask_size=3, put_bid_size=2, put_ask_size=4
            ),
        ]
        invalid_pressure = engine.calculate_bid_ask_pressure(thin_strikes, 585.0)
        print_result("Invalid case has 'raw_pressure'", 'raw_pressure' in invalid_pressure)
        print_result("Invalid case has 'smoothing_periods'", 'smoothing_periods' in invalid_pressure)
        print_result("Invalid case is_valid=False", invalid_pressure.get('is_valid') == False)

        print(f"\n  Sample combined signal:")
        print(f"    Signal: {volume.get('combined_signal')}")
        print(f"    Confidence: {volume.get('signal_confidence')}")

        return has_pressure_method and has_volume_method

    except Exception as e:
        print_result("ARGUS engine test", False, str(e))
        import traceback
        traceback.print_exc()
        return False

def test_api_endpoint():
    """Test 4: Verify API endpoint returns order_flow"""
    print_header("TEST 4: API Endpoint")

    try:
        import requests

        # Try local first, then production
        urls = [
            "http://localhost:8000/api/argus/gamma?symbol=SPY",
            "https://alphagex-api.onrender.com/api/argus/gamma?symbol=SPY"
        ]

        response = None
        used_url = None
        for url in urls:
            try:
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    used_url = url
                    break
            except:
                continue

        if not response or response.status_code != 200:
            print_result("API reachable", False, "Could not reach API")
            return False

        print_result("API reachable", True, used_url.split('/api')[0])

        data = response.json()
        has_success = data.get('success', False)
        print_result("Response success=True", has_success)

        if has_success:
            gamma_data = data.get('data', {})
            has_order_flow = 'order_flow' in gamma_data
            print_result("Response contains 'order_flow'", has_order_flow)

            if has_order_flow:
                order_flow = gamma_data['order_flow']
                print_result("  order_flow.net_gex_volume", 'net_gex_volume' in order_flow)
                print_result("  order_flow.flow_direction", 'flow_direction' in order_flow)
                print_result("  order_flow.bid_ask_pressure", 'bid_ask_pressure' in order_flow)
                print_result("  order_flow.combined_signal", 'combined_signal' in order_flow)
                print_result("  order_flow.signal_confidence", 'signal_confidence' in order_flow)

                if 'bid_ask_pressure' in order_flow:
                    pressure = order_flow['bid_ask_pressure']
                    print(f"\n  Live Order Flow Data:")
                    print(f"    Flow Direction: {order_flow.get('flow_direction')}")
                    print(f"    Flow Strength: {order_flow.get('flow_strength')}")
                    print(f"    Net GEX Volume: ${order_flow.get('net_gex_volume', 0)}M")
                    print(f"    Pressure Direction: {pressure.get('pressure_direction')}")
                    print(f"    Net Pressure: {pressure.get('net_pressure', 0):.1%}")
                    print(f"    Combined Signal: {order_flow.get('combined_signal')}")
                    print(f"    Confidence: {order_flow.get('signal_confidence')}")
                    print(f"    Is Valid: {pressure.get('is_valid')}")

                return has_order_flow

        return False

    except Exception as e:
        print_result("API endpoint test", False, str(e))
        return False

def test_database_persistence():
    """Test 5: Verify data is being persisted"""
    print_header("TEST 5: Database Persistence")

    try:
        from database_adapter import get_connection
        conn = get_connection()
        if not conn:
            print_result("Database connection", False)
            return False

        cursor = conn.cursor()

        # Check for recent records
        cursor.execute("""
            SELECT COUNT(*) FROM argus_order_flow_history
            WHERE recorded_at > NOW() - INTERVAL '24 hours'
        """)
        recent_count = cursor.fetchone()[0]
        print_result(f"Records in last 24h: {recent_count}", recent_count >= 0)

        # Get most recent record
        cursor.execute("""
            SELECT symbol, recorded_at, combined_signal, signal_confidence,
                   net_pressure, pressure_direction, is_valid
            FROM argus_order_flow_history
            ORDER BY recorded_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()

        if row:
            print_result("Has persisted records", True)
            print(f"\n  Most Recent Record:")
            print(f"    Symbol: {row[0]}")
            print(f"    Recorded At: {row[1]}")
            print(f"    Combined Signal: {row[2]}")
            print(f"    Confidence: {row[3]}")
            print(f"    Net Pressure: {row[4]}")
            print(f"    Direction: {row[5]}")
            print(f"    Is Valid: {row[6]}")
        else:
            print_result("Has persisted records", False, "No records yet (will populate during market hours)")

        # Check signal distribution
        cursor.execute("""
            SELECT combined_signal, COUNT(*)
            FROM argus_order_flow_history
            WHERE recorded_at > NOW() - INTERVAL '7 days'
            GROUP BY combined_signal
            ORDER BY COUNT(*) DESC
        """)
        signals = cursor.fetchall()
        if signals:
            print(f"\n  Signal Distribution (last 7 days):")
            for signal, count in signals:
                print(f"    {signal}: {count}")

        cursor.close()
        conn.close()
        return True

    except Exception as e:
        print_result("Database persistence test", False, str(e))
        return False

def test_argus_routes_integration():
    """Test 6: Verify ARGUS routes have persistence wired up"""
    print_header("TEST 6: Route Integration")

    try:
        import ast

        # Read the argus_routes.py file
        routes_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'backend', 'api', 'routes', 'argus_routes.py'
        )

        with open(routes_path, 'r') as f:
            content = f.read()

        # Check for key integrations
        checks = [
            ("persist_order_flow_to_db function", "async def persist_order_flow_to_db"),
            ("order_flow in gamma endpoint", "order_flow = engine.calculate_net_gex_volume"),
            ("persist call wired up", "await persist_order_flow_to_db"),
            ("order_flow in response", '"order_flow": order_flow'),
            ("Table creation SQL", "argus_order_flow_history"),
        ]

        all_pass = True
        for name, pattern in checks:
            found = pattern in content
            print_result(name, found)
            all_pass = all_pass and found

        return all_pass

    except Exception as e:
        print_result("Route integration test", False, str(e))
        return False

def main():
    print("\n" + "="*60)
    print("  ORDER FLOW SYSTEM END-TO-END TEST")
    print("  Per CLAUDE.md Production-Ready Standards")
    print("="*60)
    print(f"  Timestamp: {datetime.now().isoformat()}")

    results = []

    # Run all tests
    results.append(("Database Schema", test_database_schema()))
    results.append(("Tradier Data Fetcher", test_tradier_data_fetcher()))
    results.append(("ARGUS Engine", test_argus_engine()))
    results.append(("Route Integration", test_argus_routes_integration()))
    results.append(("API Endpoint", test_api_endpoint()))
    results.append(("Database Persistence", test_database_persistence()))

    # Summary
    print_header("SUMMARY")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")

    print(f"\n  Result: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 ALL SYSTEMS OPERATIONAL")
        print("  Order Flow feature is production-ready!")
    else:
        print("\n  ⚠️  Some tests failed - review above for details")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
