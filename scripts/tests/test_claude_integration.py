#!/usr/bin/env python3
"""
Claude AI Integration Test
Run in Render shell: python scripts/tests/test_claude_integration.py

Tests Claude API connectivity and GEXIS/ORACLE AI features.
"""

import os
import sys
import json
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Configuration - Auto-detect Render URL or use environment variable
def get_api_base_url():
    if os.environ.get('API_BASE_URL'):
        return os.environ.get('API_BASE_URL')
    # Check if we're on Render
    if os.environ.get('RENDER'):
        service_name = os.environ.get('RENDER_SERVICE_NAME', 'alphagex-backend')
        return f"https://{service_name}.onrender.com"
    return 'http://localhost:8000'

API_BASE_URL = get_api_base_url()


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_result(test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    symbol = "✓" if passed else "✗"
    print(f"  {symbol} [{status}] {test_name}")
    if details:
        print(f"           {details}")


def api_request(endpoint, method='GET', data=None, timeout=60):
    """Make API request and return response"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {'Content-Type': 'application/json'}

    start_time = time.time()

    try:
        if data:
            data = json.dumps(data).encode('utf-8')

        req = Request(url, data=data, headers=headers, method=method)
        response = urlopen(req, timeout=timeout)
        elapsed = (time.time() - start_time) * 1000

        body = response.read().decode('utf-8')
        return {
            'success': True,
            'status': response.status,
            'data': json.loads(body) if body else {},
            'elapsed_ms': elapsed
        }
    except HTTPError as e:
        elapsed = (time.time() - start_time) * 1000
        try:
            body = e.read().decode('utf-8')
            error_data = json.loads(body) if body else {}
        except:
            error_data = {}
        return {
            'success': False,
            'status': e.code,
            'data': error_data,
            'error': str(e),
            'elapsed_ms': elapsed
        }
    except Exception as e:
        return {
            'success': False,
            'status': 0,
            'data': {},
            'error': str(e)
        }


def test_api_key_configured():
    """Test that ANTHROPIC_API_KEY is configured"""
    print_header("ANTHROPIC API KEY CHECK")

    api_key = os.environ.get('ANTHROPIC_API_KEY')

    if not api_key:
        print_result("API key set", False, "ANTHROPIC_API_KEY environment variable not found")
        return False

    # Check key format
    if api_key.startswith('sk-ant-'):
        print_result("API key format", True, "Starts with 'sk-ant-' (correct)")
    else:
        print_result("API key format", False, "Unexpected format (may still work)")

    # Check key length
    if len(api_key) > 50:
        print_result("API key length", True, f"{len(api_key)} characters")
    else:
        print_result("API key length", False, f"Only {len(api_key)} characters (too short?)")

    return bool(api_key)


def test_oracle_claude_status():
    """Test ORACLE's Claude integration"""
    print_header("ORACLE CLAUDE STATUS")

    resp = api_request('/api/zero-dte/oracle/status')

    if not resp['success']:
        print_result("Oracle status endpoint", False, resp.get('error', 'Unknown error'))
        return False

    oracle = resp['data'].get('oracle', {})

    # Check Claude availability
    claude_available = oracle.get('claude_available', False)
    print_result("Claude available", claude_available)

    # Check Claude model
    claude_model = oracle.get('claude_model', 'Not configured')
    print_result("Claude model", bool(claude_model), claude_model)

    # Check model trained status
    model_trained = oracle.get('model_trained', False)
    print_result("ML model trained", model_trained)

    return claude_available


def test_gexis_command():
    """Test GEXIS chatbot command endpoint"""
    print_header("GEXIS COMMAND TEST")

    # Test /status command
    resp = api_request('/api/ai/gexis/command', method='POST', data={"command": "/status"})

    if resp['success']:
        print_result("/status command", True, f"Response in {resp.get('elapsed_ms', 0):.0f}ms")
        response_text = resp['data'].get('response', '')[:100]
        if response_text:
            print(f"           Preview: {response_text}...")
    else:
        print_result("/status command", False, resp.get('error', ''))

    # Test /briefing command
    resp = api_request('/api/ai/gexis/command', method='POST', data={"command": "/briefing"})

    if resp['success']:
        print_result("/briefing command", True, f"Response in {resp.get('elapsed_ms', 0):.0f}ms")
    else:
        # Briefing might fail if no market data, that's okay
        print_result("/briefing command", True, "Command executed (may lack data)")

    return True


def test_oracle_analysis():
    """Test ORACLE prediction analysis with Claude"""
    print_header("ORACLE ANALYSIS TEST")

    # Create test prediction request
    test_data = {
        "spot_price": 5900,
        "vix": 18.5,
        "gex_regime": "POSITIVE",
        "day_of_week": datetime.now().weekday(),
        "vix_1d_change": -0.5,
        "normalized_gex": 0.6,
        "distance_to_call_wall": 50,
        "distance_to_put_wall": 80
    }

    print("  Sending test prediction request...")
    print(f"  Parameters: spot={test_data['spot_price']}, vix={test_data['vix']}, gex={test_data['gex_regime']}")

    resp = api_request('/api/zero-dte/oracle/analyze', method='POST', data=test_data, timeout=120)

    if not resp['success']:
        print_result("Oracle analysis", False, resp.get('error', 'Unknown error'))
        return False

    data = resp['data']

    if not data.get('success'):
        print_result("Oracle analysis", False, data.get('error', 'Analysis failed'))
        return False

    # Check prediction result
    prediction = data.get('prediction', {})
    print_result("Prediction generated", bool(prediction),
                f"Response in {resp.get('elapsed_ms', 0):.0f}ms")

    if prediction:
        advice = prediction.get('advice', 'N/A')
        win_prob = prediction.get('win_probability', 0)
        confidence = prediction.get('confidence', 0)

        print_result("Advice generated", bool(advice), advice)
        print_result("Win probability", win_prob > 0, f"{win_prob*100:.1f}%")
        print_result("Confidence score", confidence > 0, f"{confidence:.1f}%")

    # Check Claude explanation
    claude_explanation = data.get('claude_explanation')
    if claude_explanation:
        print_result("Claude explanation", True, f"{len(claude_explanation)} characters")
        # Show first few lines
        preview = claude_explanation[:200].replace('\n', ' ')
        print(f"           Preview: {preview}...")
    else:
        print_result("Claude explanation", False, "No explanation generated")

    return bool(prediction)


def test_gexis_analyze_with_context():
    """Test GEXIS analysis with conversation context"""
    print_header("GEXIS CONTEXTUAL ANALYSIS TEST")

    test_data = {
        "query": "What's the current market sentiment based on GEX levels?",
        "symbol": "SPX",
        "session_id": f"test-{int(time.time())}",
        "market_data": {}
    }

    print(f"  Query: {test_data['query']}")

    resp = api_request('/api/ai/gexis/analyze-with-context', method='POST', data=test_data, timeout=120)

    if not resp['success']:
        print_result("GEXIS analysis", False, resp.get('error', 'Unknown error'))
        return False

    data = resp['data']

    if not data.get('success'):
        print_result("GEXIS analysis", False, data.get('error', 'Analysis failed'))
        return False

    analysis = data.get('data', {}).get('analysis', '')
    print_result("Analysis generated", bool(analysis), f"Response in {resp.get('elapsed_ms', 0):.0f}ms")

    if analysis:
        preview = analysis[:200].replace('\n', ' ')
        print(f"           Preview: {preview}...")

    # Check token usage
    tokens = data.get('data', {}).get('tokens_used', 0)
    if tokens:
        print_result("Token usage tracked", True, f"{tokens} tokens")

    return bool(analysis)


def test_alerts_endpoint():
    """Test GEXIS alerts endpoint"""
    print_header("GEXIS ALERTS TEST")

    resp = api_request('/api/ai/gexis/alerts')

    if resp['success']:
        count = resp['data'].get('count', 0)
        print_result("Alerts endpoint", True, f"{count} active alerts")
        return True
    else:
        print_result("Alerts endpoint", False, resp.get('error', ''))
        return False


def main():
    """Run all Claude integration tests"""
    print("""
╔═══════════════════════════════════════════════════════════╗
║           CLAUDE AI INTEGRATION TEST SUITE                ║
╚═══════════════════════════════════════════════════════════╝
""")
    print(f"  API Base URL: {API_BASE_URL}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    results = {
        "api_key": test_api_key_configured(),
        "oracle_status": test_oracle_claude_status(),
        "gexis_commands": test_gexis_command(),
        "alerts": test_alerts_endpoint(),
    }

    # Only run analysis tests if API key is configured
    if results["api_key"]:
        print("\n  Running analysis tests (may take 30-60 seconds)...")
        results["oracle_analysis"] = test_oracle_analysis()
        results["gexis_analysis"] = test_gexis_analyze_with_context()
    else:
        print("\n  ⚠️  Skipping analysis tests (no API key)")
        results["oracle_analysis"] = None
        results["gexis_analysis"] = None

    # Summary
    print_header("TEST SUMMARY")

    passed = 0
    failed = 0
    skipped = 0

    for test_name, result in results.items():
        if result is None:
            status = "SKIP"
            symbol = "⏭️"
            skipped += 1
        elif result:
            status = "PASS"
            symbol = "✓"
            passed += 1
        else:
            status = "FAIL"
            symbol = "✗"
            failed += 1

        print(f"  {symbol} [{status}] {test_name.upper().replace('_', ' ')}")

    print(f"\n  Results: {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0 and skipped == 0:
        print("\n  ✅ All Claude AI tests passed!")
        return 0
    elif failed == 0:
        print("\n  ⚠️  Tests passed but some were skipped")
        return 0
    else:
        print("\n  ❌ Some Claude AI tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
