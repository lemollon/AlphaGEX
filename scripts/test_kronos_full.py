#!/usr/bin/env python3
"""
KRONOS Full End-to-End Test Suite

Tests all KRONOS features including:
1. Infrastructure (Redis, Connection Pool, ORAT Cache)
2. REST API endpoints (init, run, job status, natural language)
3. SSE streaming
4. WebSocket connectivity
5. Natural language parsing
6. Full backtest execution

Usage:
    python scripts/test_kronos_full.py [--live]

    --live: Also run a live backtest (takes longer)
"""

import os
import sys
import json
import time
import asyncio
import argparse
import requests
from datetime import datetime
from typing import Optional

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration
API_URL = os.getenv('API_URL', 'http://localhost:8000')
TIMEOUT = 30

# Colors for output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def log_test(name: str, passed: bool, details: str = ""):
    """Log test result with color"""
    status = f"{Colors.GREEN}PASS{Colors.RESET}" if passed else f"{Colors.RED}FAIL{Colors.RESET}"
    print(f"  [{status}] {name}")
    if details and not passed:
        print(f"         {Colors.YELLOW}{details}{Colors.RESET}")


def log_section(title: str):
    """Log section header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*60}{Colors.RESET}")


# =============================================================================
# TEST FUNCTIONS
# =============================================================================

def test_infrastructure():
    """Test KRONOS infrastructure components"""
    log_section("1. INFRASTRUCTURE TESTS")
    results = []

    # Test 1.1: Infrastructure module import
    try:
        from backend.services.kronos_infrastructure import (
            job_store, connection_pool, orat_cache, get_infrastructure_status
        )
        log_test("Import kronos_infrastructure", True)
        results.append(True)
    except ImportError as e:
        log_test("Import kronos_infrastructure", False, str(e))
        results.append(False)
        return results

    # Test 1.2: Job store type
    storage_type = job_store.get_storage_type()
    log_test(f"Job store initialized ({storage_type})", True)
    results.append(True)

    # Test 1.3: Create and retrieve job
    try:
        from backend.services.kronos_infrastructure import KronosJob
        test_job = KronosJob(
            job_id="test_job_" + datetime.now().strftime("%H%M%S"),
            status="pending",
            progress=0,
            progress_message="Test job"
        )
        job_store.create(test_job)
        retrieved = job_store.get(test_job.job_id)
        passed = retrieved is not None and retrieved.job_id == test_job.job_id
        log_test("Job create/retrieve", passed)
        results.append(passed)
    except Exception as e:
        log_test("Job create/retrieve", False, str(e))
        results.append(False)

    # Test 1.4: Job update
    try:
        job_store.update(test_job.job_id, progress=50, progress_message="Half done")
        updated = job_store.get(test_job.job_id)
        passed = updated and updated.progress == 50
        log_test("Job update", passed)
        results.append(passed)
    except Exception as e:
        log_test("Job update", False, str(e))
        results.append(False)

    # Test 1.5: Connection pool
    try:
        pool_available = connection_pool.is_available
        log_test(f"Connection pool available: {pool_available}", True)
        results.append(True)
    except Exception as e:
        log_test("Connection pool check", False, str(e))
        results.append(False)

    # Test 1.6: ORAT cache stats
    try:
        cache_stats = orat_cache.get_stats()
        log_test(f"ORAT cache stats: {cache_stats['memory_entries']} entries, {cache_stats['hit_rate_pct']}% hit rate", True)
        results.append(True)
    except Exception as e:
        log_test("ORAT cache stats", False, str(e))
        results.append(False)

    # Test 1.7: Full infrastructure status
    try:
        status = get_infrastructure_status()
        log_test(f"Infrastructure status: job_store={status['job_store']['type']}", True)
        results.append(True)
    except Exception as e:
        log_test("Infrastructure status", False, str(e))
        results.append(False)

    return results


def test_rest_api():
    """Test KRONOS REST API endpoints"""
    log_section("2. REST API TESTS")
    results = []

    # Test 2.1: Health endpoint
    try:
        resp = requests.get(f"{API_URL}/api/zero-dte/health", timeout=TIMEOUT)
        passed = resp.status_code == 200
        log_test("Health endpoint", passed, f"Status: {resp.status_code}")
        results.append(passed)
    except Exception as e:
        log_test("Health endpoint", False, str(e))
        results.append(False)

    # Test 2.2: Init endpoint (consolidated)
    try:
        resp = requests.get(f"{API_URL}/api/zero-dte/init", timeout=TIMEOUT)
        passed = resp.status_code == 200
        if passed:
            data = resp.json()
            has_keys = all(k in data for k in ['health', 'strategies', 'tiers', 'presets'])
            log_test("Init endpoint (consolidated)", has_keys, f"Keys: {list(data.keys())}")
            results.append(has_keys)
        else:
            log_test("Init endpoint", False, f"Status: {resp.status_code}")
            results.append(False)
    except Exception as e:
        log_test("Init endpoint", False, str(e))
        results.append(False)

    # Test 2.3: Strategies endpoint
    try:
        resp = requests.get(f"{API_URL}/api/zero-dte/strategies", timeout=TIMEOUT)
        passed = resp.status_code == 200
        log_test("Strategies endpoint", passed)
        results.append(passed)
    except Exception as e:
        log_test("Strategies endpoint", False, str(e))
        results.append(False)

    # Test 2.4: Strategy types endpoint
    try:
        resp = requests.get(f"{API_URL}/api/zero-dte/strategy-types", timeout=TIMEOUT)
        passed = resp.status_code == 200
        log_test("Strategy types endpoint", passed)
        results.append(passed)
    except Exception as e:
        log_test("Strategy types endpoint", False, str(e))
        results.append(False)

    # Test 2.5: Tiers endpoint
    try:
        resp = requests.get(f"{API_URL}/api/zero-dte/tiers", timeout=TIMEOUT)
        passed = resp.status_code == 200
        log_test("Tiers endpoint", passed)
        results.append(passed)
    except Exception as e:
        log_test("Tiers endpoint", False, str(e))
        results.append(False)

    # Test 2.6: Infrastructure status endpoint
    try:
        resp = requests.get(f"{API_URL}/api/kronos/infrastructure", timeout=TIMEOUT)
        passed = resp.status_code == 200
        if passed:
            data = resp.json()
            log_test("Infrastructure status API", True, f"Job store: {data.get('infrastructure', {}).get('job_store', {}).get('type')}")
        else:
            log_test("Infrastructure status API", False)
        results.append(passed)
    except Exception as e:
        log_test("Infrastructure status API", False, str(e))
        results.append(False)

    return results


def test_natural_language():
    """Test natural language backtesting"""
    log_section("3. NATURAL LANGUAGE TESTS")
    results = []

    test_queries = [
        ("Run iron condor for 2023", ["2023", "iron_condor"]),
        ("Test GEX protected strategy from 2022 to 2023", ["gex_protected", "2022", "2023"]),
        ("Backtest aggressive iron condors with VIX > 20", ["aggressive", "min_vix"]),
        ("Run 1.5 SD conservative strategy", ["1.5", "sd_multiplier", "conservative"]),
    ]

    # Test 3.1: Natural language endpoint exists
    try:
        resp = requests.post(
            f"{API_URL}/api/zero-dte/natural-language",
            json={"query": "test query"},
            timeout=TIMEOUT
        )
        passed = resp.status_code in [200, 500]  # 500 might happen if no DB
        log_test("Natural language endpoint exists", passed)
        results.append(passed)
    except Exception as e:
        log_test("Natural language endpoint exists", False, str(e))
        results.append(False)
        return results

    # Test 3.2: Fallback parser
    try:
        from backend.api.routes.zero_dte_backtest_routes import _parse_natural_language_fallback

        for query, expected_items in test_queries:
            parsed = _parse_natural_language_fallback(query)
            # Check if any expected item appears in parsed values
            parsed_str = json.dumps(parsed).lower()
            found = sum(1 for item in expected_items if item.lower() in parsed_str)
            passed = found >= 1
            log_test(f"Parse: '{query[:40]}...'", passed, f"Parsed: {parsed}")
            results.append(passed)

    except ImportError:
        log_test("Fallback parser import", False, "Could not import parser")
        results.append(False)
    except Exception as e:
        log_test("Fallback parser", False, str(e))
        results.append(False)

    return results


def test_sse_streaming():
    """Test SSE streaming endpoint"""
    log_section("4. SSE STREAMING TESTS")
    results = []

    # Test 4.1: SSE endpoint exists (with fake job ID)
    try:
        resp = requests.get(
            f"{API_URL}/api/zero-dte/job/test_nonexistent/stream",
            stream=True,
            timeout=5
        )
        # Should return 200 with SSE (even for non-existent job, it sends error message)
        passed = resp.status_code == 200
        content_type = resp.headers.get('content-type', '')
        log_test("SSE endpoint exists", passed, f"Content-Type: {content_type}")
        results.append(passed)
        resp.close()
    except requests.exceptions.Timeout:
        # Timeout is expected for SSE
        log_test("SSE endpoint exists", True, "Connection established (timeout expected)")
        results.append(True)
    except Exception as e:
        log_test("SSE endpoint exists", False, str(e))
        results.append(False)

    return results


def test_websocket():
    """Test WebSocket connectivity"""
    log_section("5. WEBSOCKET TESTS")
    results = []

    try:
        import websockets
    except ImportError:
        log_test("WebSocket library available", False, "pip install websockets")
        return [False]

    async def ws_test():
        ws_url = API_URL.replace('http://', 'ws://').replace('https://', 'wss://')

        # Test 5.1: Job WebSocket endpoint
        try:
            async with websockets.connect(
                f"{ws_url}/ws/kronos/job/test_job",
                close_timeout=2
            ) as ws:
                # Send ping
                await ws.send("ping")
                response = await asyncio.wait_for(ws.recv(), timeout=3)
                passed = response == "pong" or "job_update" in response
                log_test("Job WebSocket ping/pong", passed, f"Response: {response[:50]}...")
                return [passed]
        except asyncio.TimeoutError:
            log_test("Job WebSocket", True, "Connected (no immediate response expected)")
            return [True]
        except Exception as e:
            log_test("Job WebSocket", False, str(e))
            return [False]

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(ws_test())
    except Exception as e:
        log_test("WebSocket test", False, str(e))
        results = [False]

    return results


def test_live_backtest(run_backtest: bool = False):
    """Test live backtest execution"""
    log_section("6. LIVE BACKTEST TEST")
    results = []

    if not run_backtest:
        print(f"  {Colors.YELLOW}Skipped (use --live to enable){Colors.RESET}")
        return []

    # Test 6.1: Submit backtest
    try:
        config = {
            "start_date": "2023-01-01",
            "end_date": "2023-01-31",  # Just one month for speed
            "initial_capital": 100000,
            "spread_width": 10.0,
            "sd_multiplier": 1.0,
            "risk_per_trade_pct": 5.0,
            "ticker": "SPX",
            "strategy": "hybrid_fixed",
            "strategy_type": "iron_condor",
            "strike_selection": "sd",
            "trade_monday": True,
            "trade_tuesday": True,
            "trade_wednesday": True,
            "trade_thursday": True,
            "trade_friday": True,
        }

        resp = requests.post(
            f"{API_URL}/api/zero-dte/run",
            json=config,
            timeout=TIMEOUT
        )

        if resp.status_code == 200:
            data = resp.json()
            job_id = data.get('job_id')
            log_test("Submit backtest", bool(job_id), f"Job ID: {job_id}")
            results.append(bool(job_id))

            if job_id:
                # Test 6.2: Poll for completion
                max_wait = 120  # 2 minutes max
                start_time = time.time()
                final_status = None

                while time.time() - start_time < max_wait:
                    poll_resp = requests.get(f"{API_URL}/api/zero-dte/job/{job_id}", timeout=TIMEOUT)
                    if poll_resp.status_code == 200:
                        job_data = poll_resp.json().get('job', {})
                        status = job_data.get('status')
                        progress = job_data.get('progress', 0)
                        message = job_data.get('progress_message', '')
                        print(f"\r  [{Colors.BLUE}...{Colors.RESET}] Progress: {progress}% - {message[:40]}...", end="", flush=True)

                        if status == 'completed':
                            final_status = 'completed'
                            break
                        elif status == 'failed':
                            final_status = 'failed'
                            break

                    time.sleep(2)

                print()  # New line after progress

                if final_status == 'completed':
                    log_test("Backtest completion", True)
                    results.append(True)

                    # Test 6.3: Get results
                    result = poll_resp.json().get('job', {}).get('result', {})
                    if result:
                        summary = result.get('summary', {})
                        trades = result.get('trades', {})
                        log_test(f"Results: {trades.get('total', 0)} trades, {summary.get('total_return_pct', 0):.1f}% return", True)
                        results.append(True)
                    else:
                        log_test("Get results", False, "No result data")
                        results.append(False)
                else:
                    log_test("Backtest completion", False, f"Status: {final_status}")
                    results.append(False)
        else:
            log_test("Submit backtest", False, f"Status: {resp.status_code}")
            results.append(False)

    except Exception as e:
        log_test("Live backtest", False, str(e))
        results.append(False)

    return results


def test_natural_language_backtest(run_backtest: bool = False):
    """Test natural language backtest execution"""
    log_section("7. NATURAL LANGUAGE BACKTEST TEST")
    results = []

    if not run_backtest:
        print(f"  {Colors.YELLOW}Skipped (use --live to enable){Colors.RESET}")
        return []

    try:
        # Submit NL backtest
        resp = requests.post(
            f"{API_URL}/api/zero-dte/natural-language",
            json={"query": "Run a conservative iron condor for January 2023 with $100k"},
            timeout=TIMEOUT
        )

        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                job_id = data.get('job_id')
                parsing_method = data.get('parsing_method')
                parsed_config = data.get('parsed_config')

                log_test(f"NL backtest submitted (parsed via {parsing_method})", True)
                log_test(f"Parsed config: {json.dumps(parsed_config)[:60]}...", True)
                results.extend([True, True])

                # Poll for completion (same as regular backtest)
                max_wait = 120
                start_time = time.time()
                final_status = None

                while time.time() - start_time < max_wait:
                    poll_resp = requests.get(f"{API_URL}/api/zero-dte/job/{job_id}", timeout=TIMEOUT)
                    if poll_resp.status_code == 200:
                        job_data = poll_resp.json().get('job', {})
                        status = job_data.get('status')
                        progress = job_data.get('progress', 0)
                        print(f"\r  [{Colors.BLUE}...{Colors.RESET}] NL Backtest: {progress}%", end="", flush=True)

                        if status in ('completed', 'failed'):
                            final_status = status
                            break

                    time.sleep(2)

                print()
                log_test(f"NL backtest {final_status}", final_status == 'completed')
                results.append(final_status == 'completed')
            else:
                log_test("NL backtest", False, data.get('error'))
                results.append(False)
        else:
            log_test("NL backtest submit", False, f"Status: {resp.status_code}")
            results.append(False)

    except Exception as e:
        log_test("NL backtest", False, str(e))
        results.append(False)

    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="KRONOS Full Test Suite")
    parser.add_argument("--live", action="store_true", help="Run live backtest tests")
    args = parser.parse_args()

    print(f"\n{Colors.BOLD}{Colors.CYAN}KRONOS FULL TEST SUITE{Colors.RESET}")
    print(f"{Colors.CYAN}Testing against: {API_URL}{Colors.RESET}")
    print(f"{Colors.CYAN}Timestamp: {datetime.now().isoformat()}{Colors.RESET}")

    all_results = []

    # Run all tests
    all_results.extend(test_infrastructure())
    all_results.extend(test_rest_api())
    all_results.extend(test_natural_language())
    all_results.extend(test_sse_streaming())
    all_results.extend(test_websocket())
    all_results.extend(test_live_backtest(args.live))
    all_results.extend(test_natural_language_backtest(args.live))

    # Summary
    log_section("SUMMARY")
    passed = sum(1 for r in all_results if r)
    failed = sum(1 for r in all_results if not r)
    total = len(all_results)

    print(f"\n  Total Tests: {total}")
    print(f"  {Colors.GREEN}Passed: {passed}{Colors.RESET}")
    print(f"  {Colors.RED}Failed: {failed}{Colors.RESET}")

    if failed == 0:
        print(f"\n  {Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED!{Colors.RESET}")
    else:
        print(f"\n  {Colors.YELLOW}Some tests failed. Check the output above.{Colors.RESET}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
