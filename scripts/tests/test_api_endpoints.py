#!/usr/bin/env python3
"""
API Endpoint Testing Script
Run in Render shell: python scripts/tests/test_api_endpoints.py

Tests all major API endpoints for AlphaGEX.
Set API_BASE_URL environment variable or defaults to http://localhost:8000
"""

import os
import sys
import json
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Configuration
API_BASE_URL = os.environ.get('API_BASE_URL', 'http://localhost:8000')


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test_name, passed, details="", response_time=None):
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    time_str = f" ({response_time:.0f}ms)" if response_time else ""
    print(f"  {symbol} [{status}]{time_str} {test_name}")
    if details:
        print(f"           {details}")


def api_request(endpoint, method='GET', data=None, timeout=30):
    """Make API request and return response"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    start_time = time.time()

    try:
        if data:
            data = json.dumps(data).encode('utf-8')

        req = Request(url, data=data, headers=headers, method=method)
        response = urlopen(req, timeout=timeout)
        response_time = (time.time() - start_time) * 1000

        body = response.read().decode('utf-8')
        return {
            'success': True,
            'status': response.status,
            'data': json.loads(body) if body else {},
            'response_time': response_time
        }
    except HTTPError as e:
        response_time = (time.time() - start_time) * 1000
        try:
            body = e.read().decode('utf-8')
            error_data = json.loads(body) if body else {}
        except:
            error_data = {'error': str(e)}
        return {
            'success': False,
            'status': e.code,
            'data': error_data,
            'response_time': response_time,
            'error': str(e)
        }
    except URLError as e:
        return {
            'success': False,
            'status': 0,
            'data': {},
            'error': str(e.reason)
        }
    except Exception as e:
        return {
            'success': False,
            'status': 0,
            'data': {},
            'error': str(e)
        }


def test_health_endpoints():
    """Test health check endpoints"""
    print_header("HEALTH CHECK ENDPOINTS")
    results = []

    # Test root endpoint
    resp = api_request('/')
    results.append(resp['success'] or resp['status'] == 200)
    print_result("GET /", resp['success'] or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Test health endpoint
    resp = api_request('/health')
    passed = resp['success'] and resp['data'].get('status') == 'healthy'
    results.append(passed)
    print_result("GET /health", passed,
                resp['data'].get('status', resp.get('error', '')),
                response_time=resp.get('response_time'))

    return all(results)


def test_market_data_endpoints():
    """Test market data endpoints"""
    print_header("MARKET DATA ENDPOINTS")
    results = []

    # GEX endpoints
    resp = api_request('/api/gex/latest?symbol=SPX')
    passed = resp['success'] or resp['status'] in [200, 404]
    results.append(passed)
    print_result("GET /api/gex/latest", passed,
                response_time=resp.get('response_time'))

    resp = api_request('/api/gex/levels?symbol=SPX')
    passed = resp['success'] or resp['status'] in [200, 404]
    results.append(passed)
    print_result("GET /api/gex/levels", passed,
                response_time=resp.get('response_time'))

    # Market psychology
    resp = api_request('/api/psychology/latest')
    passed = resp['success'] or resp['status'] in [200, 404]
    results.append(passed)
    print_result("GET /api/psychology/latest", passed,
                response_time=resp.get('response_time'))

    # VIX data
    resp = api_request('/api/vix/latest')
    passed = resp['success'] or resp['status'] in [200, 404]
    results.append(passed)
    print_result("GET /api/vix/latest", passed,
                response_time=resp.get('response_time'))

    return all(results)


def test_pythia_endpoints():
    """Test PYTHIA (probability system) endpoints"""
    print_header("PYTHIA (PROBABILITY) ENDPOINTS")
    results = []

    # Get outcomes
    resp = api_request('/api/probability/outcomes?days=30')
    passed = resp['success'] and resp['data'].get('success', False)
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/probability/outcomes", passed or resp['status'] == 200,
                f"outcomes: {len(resp['data'].get('outcomes', []))}" if passed else resp.get('error', ''),
                response_time=resp.get('response_time'))

    # Get weights
    resp = api_request('/api/probability/weights')
    passed = resp['success'] and resp['data'].get('success', False)
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/probability/weights", passed or resp['status'] == 200,
                f"weights: {len(resp['data'].get('weights', []))}" if passed else resp.get('error', ''),
                response_time=resp.get('response_time'))

    # Get calibration history
    resp = api_request('/api/probability/calibration-history?days=90')
    passed = resp['success'] and resp['data'].get('success', False)
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/probability/calibration-history", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_oracle_endpoints():
    """Test ORACLE AI endpoints"""
    print_header("ORACLE AI ENDPOINTS")
    results = []

    # Get status
    resp = api_request('/api/zero-dte/oracle/status')
    passed = resp['success'] and resp['data'].get('success', False)
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/zero-dte/oracle/status", passed or resp['status'] == 200,
                f"model_trained: {resp['data'].get('oracle', {}).get('model_trained', 'N/A')}" if passed else '',
                response_time=resp.get('response_time'))

    # Get logs
    resp = api_request('/api/zero-dte/oracle/logs')
    passed = resp['success'] and resp['data'].get('success', False)
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/zero-dte/oracle/logs", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get predictions history
    resp = api_request('/api/logs/oracle?limit=10')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/logs/oracle", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_ml_endpoints():
    """Test PROMETHEUS (ML system) endpoints"""
    print_header("PROMETHEUS (ML) ENDPOINTS")
    results = []

    # Get ML status
    resp = api_request('/api/ml/status')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ml/status", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get feature importance
    resp = api_request('/api/ml/feature-importance')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ml/feature-importance", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get strategy explanation
    resp = api_request('/api/ml/strategy-explanation')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ml/strategy-explanation", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get data quality
    resp = api_request('/api/ml/data-quality')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ml/data-quality", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get ML logs
    resp = api_request('/api/ml/logs?limit=10')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ml/logs", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_wheel_endpoints():
    """Test Wheel Strategy endpoints"""
    print_header("WHEEL STRATEGY ENDPOINTS")
    results = []

    # Get phases
    resp = api_request('/api/wheel/phases')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/wheel/phases", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get active cycles
    resp = api_request('/api/wheel/active')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/wheel/active", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get summary
    resp = api_request('/api/wheel/summary')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/wheel/summary", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get cycles by status
    resp = api_request('/api/wheel/cycles?status=CALLED_AWAY')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/wheel/cycles?status=CALLED_AWAY", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_trader_endpoints():
    """Test Autonomous Trader endpoints"""
    print_header("AUTONOMOUS TRADER ENDPOINTS")
    results = []

    # Get status
    resp = api_request('/api/trader/status')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/trader/status", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get live status
    resp = api_request('/api/trader/live-status')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/trader/live-status", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get performance
    resp = api_request('/api/trader/performance')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/trader/performance", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get diagnostics
    resp = api_request('/api/trader/diagnostics')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/trader/diagnostics", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_backtest_endpoints():
    """Test KRONOS backtest endpoints"""
    print_header("KRONOS BACKTEST ENDPOINTS")
    results = []

    # Get jobs list
    resp = api_request('/api/zero-dte/jobs')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/zero-dte/jobs", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get patterns
    resp = api_request('/api/zero-dte/patterns')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/zero-dte/patterns", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_gexis_endpoints():
    """Test GEXIS chatbot endpoints"""
    print_header("GEXIS CHATBOT ENDPOINTS")
    results = []

    # Get alerts
    resp = api_request('/api/ai/gexis/alerts')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ai/gexis/alerts", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get conversations
    resp = api_request('/api/ai/conversations?limit=10')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/ai/conversations", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def test_decision_log_endpoints():
    """Test Decision Log endpoints"""
    print_header("DECISION LOG ENDPOINTS")
    results = []

    # Get decision logs
    resp = api_request('/api/logs/decisions?limit=10')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/logs/decisions", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get logs for specific bot
    for bot in ['ARES', 'ATLAS', 'PHOENIX', 'HERMES', 'ORACLE']:
        resp = api_request(f'/api/logs/decisions?bot_name={bot}&limit=5')
        passed = resp['success']
        results.append(passed or resp['status'] == 200)
        print_result(f"GET /api/logs/decisions?bot_name={bot}", passed or resp['status'] == 200,
                    response_time=resp.get('response_time'))

    return all(results)


def test_optimizer_endpoints():
    """Test Strike Optimizer endpoints"""
    print_header("STRIKE OPTIMIZER ENDPOINTS")
    results = []

    # Get optimization results
    resp = api_request('/api/optimizer/results')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/optimizer/results", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get metrics
    resp = api_request('/api/optimizer/metrics')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/optimizer/metrics", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    # Get greeks performance
    resp = api_request('/api/optimizer/greeks')
    passed = resp['success']
    results.append(passed or resp['status'] == 200)
    print_result("GET /api/optimizer/greeks", passed or resp['status'] == 200,
                response_time=resp.get('response_time'))

    return all(results)


def main():
    """Run all API endpoint tests"""
    print("\n" + "="*60)
    print("  ALPHAGEX API ENDPOINT TEST SUITE")
    print(f"  Base URL: {API_BASE_URL}")
    print("  " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("="*60)

    results = {
        "health": test_health_endpoints(),
        "market_data": test_market_data_endpoints(),
        "pythia": test_pythia_endpoints(),
        "oracle": test_oracle_endpoints(),
        "prometheus": test_ml_endpoints(),
        "wheel": test_wheel_endpoints(),
        "trader": test_trader_endpoints(),
        "kronos": test_backtest_endpoints(),
        "gexis": test_gexis_endpoints(),
        "decision_logs": test_decision_log_endpoints(),
        "optimizer": test_optimizer_endpoints(),
    }

    # Summary
    print_header("TEST SUMMARY")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        print_result(test_name.upper(), result)

    print(f"\n  Overall: {passed}/{total} test groups passed")

    if passed == total:
        print("\n  ✅ All API endpoint tests passed!")
        return 0
    else:
        print("\n  ⚠️  Some tests failed. Check above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
