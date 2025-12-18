#!/usr/bin/env python3
"""
End-to-End Test for ATHENA Directional Strategy

Tests:
1. ATHENA trader initialization
2. ML signal generation
3. API endpoints
4. Database logging
5. Full trading cycle
6. Data flow verification

Usage:
    # Test against deployed API
    API_URL=https://alphagex-api.onrender.com python scripts/test_athena_e2e.py

    # Test against local API
    python scripts/test_athena_e2e.py
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# Configuration
API_URL = os.environ.get('API_URL', 'http://localhost:8000')
VERBOSE = os.environ.get('VERBOSE', '1') == '1'

def log(msg, level='INFO'):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] [{level}] {msg}")

def test_result(name, passed, details=None):
    status = '✅ PASS' if passed else '❌ FAIL'
    print(f"\n{status}: {name}")
    if details and VERBOSE:
        if isinstance(details, dict):
            for k, v in details.items():
                print(f"    {k}: {v}")
        else:
            print(f"    {details}")
    return passed

def test_api_health():
    """Test 1: API Health Check"""
    try:
        # Try /health first (FastAPI standard), fallback to /api/health
        resp = requests.get(f"{API_URL}/health", timeout=10)
        if resp.status_code == 404:
            resp = requests.get(f"{API_URL}/api/health", timeout=10)
        return test_result(
            "API Health Check",
            resp.status_code == 200,
            resp.json() if resp.status_code == 200 else f"Status: {resp.status_code}"
        )
    except Exception as e:
        return test_result("API Health Check", False, str(e))

def test_athena_status():
    """Test 2: ATHENA Status Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/status", timeout=15)
        if resp.status_code != 200:
            return test_result("ATHENA Status", False, f"Status: {resp.status_code}")

        data = resp.json().get('data', {})
        details = {
            'mode': data.get('mode', 'unknown'),
            'capital': f"${data.get('capital', 0):,.0f}",
            'gex_ml_available': data.get('gex_ml_available', False),
            'oracle_available': data.get('oracle_available', False),
            'kronos_available': data.get('kronos_available', False),
            'is_active': data.get('is_active', False)
        }

        # Pass if we got a response with expected fields
        passed = 'mode' in data and 'capital' in data
        return test_result("ATHENA Status", passed, details)
    except Exception as e:
        return test_result("ATHENA Status", False, str(e))

def test_ml_signal():
    """Test 3: ML Signal Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/ml-signal", timeout=20)
        if resp.status_code == 503:
            return test_result("ML Signal", False, "ATHENA not available (503)")
        if resp.status_code != 200:
            return test_result("ML Signal", False, f"Status: {resp.status_code}")

        result = resp.json()
        data = result.get('data')

        if data is None:
            msg = result.get('message', 'No data')
            return test_result("ML Signal", True, f"No signal: {msg}")

        details = {
            'advice': data.get('advice'),
            'spread_type': data.get('spread_type'),
            'confidence': f"{data.get('confidence', 0) * 100:.1f}%",
            'win_probability': f"{data.get('win_probability', 0) * 100:.1f}%",
            'reasoning': data.get('reasoning', '')[:100] + '...' if data.get('reasoning') else 'N/A'
        }

        # Check model predictions
        if data.get('model_predictions'):
            mp = data['model_predictions']
            details['direction'] = mp.get('direction')
            details['flip_gravity'] = f"{mp.get('flip_gravity', 0) * 100:.0f}%"
            details['pin_zone'] = f"{mp.get('pin_zone', 0) * 100:.0f}%"

        # Check GEX context
        if data.get('gex_context'):
            gc = data['gex_context']
            details['spot_price'] = gc.get('spot_price')
            details['regime'] = gc.get('regime')

        passed = data.get('advice') in ['LONG', 'SHORT', 'STAY_OUT']
        return test_result("ML Signal", passed, details)
    except Exception as e:
        return test_result("ML Signal", False, str(e))

def test_oracle_advice():
    """Test 4: Oracle Advice Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/oracle-advice", timeout=15)
        if resp.status_code != 200:
            return test_result("Oracle Advice", False, f"Status: {resp.status_code}")

        result = resp.json()
        data = result.get('data')

        if data is None:
            return test_result("Oracle Advice", True, "No oracle advice available")

        details = {
            'advice': data.get('advice'),
            'confidence': f"{data.get('confidence', 0) * 100:.1f}%",
            'win_probability': f"{data.get('win_probability', 0) * 100:.1f}%",
            'reasoning': data.get('reasoning', '')[:100] + '...' if data.get('reasoning') else 'N/A'
        }

        return test_result("Oracle Advice", True, details)
    except Exception as e:
        return test_result("Oracle Advice", False, str(e))

def test_signals_history():
    """Test 5: Signals History Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/signals?limit=5", timeout=15)
        if resp.status_code != 200:
            return test_result("Signals History", False, f"Status: {resp.status_code}")

        data = resp.json().get('data', [])
        details = {
            'count': len(data),
            'latest_signal': data[0].get('direction', data[0].get('signal_direction')) if data else 'None'
        }

        if data:
            latest = data[0]
            details['latest_date'] = latest.get('created_at', 'unknown')[:19]
            conf = latest.get('confidence', latest.get('ml_confidence', 0))
            details['latest_confidence'] = f"{conf * 100:.1f}%"

        return test_result("Signals History", True, details)
    except Exception as e:
        return test_result("Signals History", False, str(e))

def test_positions():
    """Test 6: Positions Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/positions", timeout=15)
        if resp.status_code != 200:
            return test_result("Positions", False, f"Status: {resp.status_code}")

        data = resp.json().get('data', [])
        # Handle both uppercase and lowercase status values
        open_positions = [p for p in data if p.get('status', '').lower() == 'open']
        closed_positions = [p for p in data if p.get('status', '').lower() == 'closed']

        details = {
            'total': len(data),
            'open': len(open_positions),
            'closed': len(closed_positions)
        }

        if closed_positions:
            total_pnl = sum(p.get('realized_pnl', 0) for p in closed_positions)
            details['total_pnl'] = f"${total_pnl:,.2f}"

        return test_result("Positions", True, details)
    except Exception as e:
        return test_result("Positions", False, str(e))

def test_performance():
    """Test 7: Performance Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/performance?days=30", timeout=15)
        if resp.status_code != 200:
            return test_result("Performance", False, f"Status: {resp.status_code}")

        result = resp.json().get('data', {})
        summary = result.get('summary', {})

        details = {
            'total_trades': summary.get('total_trades', 0),
            'total_wins': summary.get('total_wins', 0),
            'total_pnl': f"${summary.get('total_pnl', 0):,.2f}",
            'avg_win_rate': f"{summary.get('avg_win_rate', 0) * 100:.1f}%"
        }

        return test_result("Performance", True, details)
    except Exception as e:
        return test_result("Performance", False, str(e))

def test_logs():
    """Test 8: Logs Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/logs?limit=10", timeout=15)
        if resp.status_code != 200:
            return test_result("Logs", False, f"Status: {resp.status_code}")

        data = resp.json().get('data', [])

        by_level = {}
        for log in data:
            level = log.get('level', 'UNKNOWN')
            by_level[level] = by_level.get(level, 0) + 1

        details = {
            'total_logs': len(data),
            'levels': by_level
        }

        if data:
            details['latest'] = data[0].get('message', 'N/A')[:60]

        return test_result("Logs", True, details)
    except Exception as e:
        return test_result("Logs", False, str(e))

def test_run_cycle():
    """Test 9: Run Trading Cycle (if market hours)"""
    try:
        # First check if we should run during market hours
        from datetime import datetime
        import pytz

        ny_tz = pytz.timezone('America/New_York')
        now = datetime.now(ny_tz)

        # Check if market is open (9:30 AM - 4:00 PM ET, Mon-Fri)
        is_weekday = now.weekday() < 5
        is_market_hours = now.hour >= 9 and now.hour < 16

        if not (is_weekday and is_market_hours):
            return test_result(
                "Run Cycle",
                True,
                f"Skipped (market closed). Current time: {now.strftime('%Y-%m-%d %H:%M %Z')}"
            )

        # Run the cycle (endpoint is /api/athena/run)
        resp = requests.post(f"{API_URL}/api/athena/run", timeout=60)
        if resp.status_code != 200:
            return test_result("Run Cycle", False, f"Status: {resp.status_code}")

        result = resp.json().get('data', {})
        details = {
            'signal_source': result.get('signal_source', 'N/A'),
            'trades_attempted': result.get('trades_attempted', 0),
            'trades_executed': result.get('trades_executed', 0),
            'positions_closed': result.get('positions_closed', 0),
            'daily_pnl': f"${result.get('daily_pnl', 0):,.2f}"
        }

        return test_result("Run Cycle", True, details)
    except ImportError:
        return test_result("Run Cycle", True, "Skipped (pytz not installed)")
    except Exception as e:
        return test_result("Run Cycle", False, str(e))

def test_diagnostics():
    """Test 10: Diagnostics Endpoint"""
    try:
        resp = requests.get(f"{API_URL}/api/athena/diagnostics", timeout=20)
        if resp.status_code != 200:
            return test_result("Diagnostics", False, f"Status: {resp.status_code}")

        data = resp.json().get('data', {})

        # Extract key info
        subsystems = data.get('subsystems', {})
        data_avail = data.get('data_availability', {})
        env = data.get('environment', {})

        details = {
            'athena_available': data.get('athena_available'),
            'kronos': subsystems.get('kronos', {}).get('available'),
            'oracle': subsystems.get('oracle', {}).get('available'),
            'gex_ml': subsystems.get('gex_ml', {}).get('available'),
            'gex_data_source': data_avail.get('gex_data', {}).get('source'),
            'ml_model_exists': data_avail.get('ml_model_file', {}).get('exists'),
            'database_url_set': env.get('database_url')
        }

        # Check database GEX data
        db_gex = data_avail.get('database_gex', [])
        if isinstance(db_gex, list) and db_gex:
            details['latest_gex_symbol'] = db_gex[0].get('symbol')
            details['latest_gex_date'] = db_gex[0].get('latest_date')

        return test_result("Diagnostics", True, details)
    except Exception as e:
        return test_result("Diagnostics", False, str(e))

def main():
    print("=" * 70)
    print("ATHENA DIRECTIONAL STRATEGY - END-TO-END TEST")
    print("=" * 70)
    print(f"API URL: {API_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    tests = [
        test_api_health,
        test_athena_status,
        test_ml_signal,
        test_oracle_advice,
        test_signals_history,
        test_positions,
        test_performance,
        test_logs,
        test_diagnostics,
        test_run_cycle,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            log(f"Test {test.__name__} crashed: {e}", "ERROR")
            results.append(False)
        time.sleep(0.5)  # Rate limiting

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(results)
    total = len(results)
    print(f"Tests Passed: {passed}/{total}")
    print(f"Success Rate: {passed/total*100:.0f}%")

    if passed == total:
        print("\n✅ ALL TESTS PASSED - ATHENA is ready for trading!")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - review above for details")

    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())
