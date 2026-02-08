#!/usr/bin/env python3
"""
Test API endpoints via HTTP requests.
Run from Render shell: python scripts/test_api_endpoints.py [base_url]

Default base_url: http://localhost:8000
For production: python scripts/test_api_endpoints.py https://alphagex-api.onrender.com
"""

import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime
from zoneinfo import ZoneInfo

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Default timeout for requests
TIMEOUT = 30


def fetch_json(url: str) -> dict:
    """Fetch JSON from URL"""
    try:
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/json')
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"URL Error: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def test_endpoint(base_url: str, path: str, expected_keys: list = None) -> dict:
    """Test a single endpoint"""
    url = f"{base_url}{path}"
    print(f"\n  Testing: {path}")

    result = fetch_json(url)

    if "error" in result:
        print(f"    {RED}✗ ERROR: {result['error']}{RESET}")
        return {"status": "error", "error": result["error"]}

    # Check for success field
    if "success" in result:
        if result["success"]:
            print(f"    {GREEN}✓ Response: success=true{RESET}")
        else:
            msg = result.get("message", result.get("error", "Unknown"))
            print(f"    {YELLOW}⚠ Response: success=false - {msg}{RESET}")
            return {"status": "failed", "message": msg}

    # Check expected keys
    if expected_keys:
        missing = [k for k in expected_keys if k not in result]
        if missing:
            print(f"    {YELLOW}⚠ Missing keys: {missing}{RESET}")
        else:
            print(f"    {GREEN}✓ Has expected keys: {expected_keys}{RESET}")

    # Check for data
    if "data" in result:
        data = result["data"]
        if isinstance(data, list):
            print(f"    Data: {len(data)} items")
        elif isinstance(data, dict):
            print(f"    Data keys: {list(data.keys())[:5]}...")

    return {"status": "ok", "result": result}


def test_equity_curve(base_url: str, bot: str, endpoint: str):
    """Test equity curve endpoint and verify daily_pnl"""
    url = f"{base_url}/api/{bot}/{endpoint}"
    print(f"\n  Testing: /api/{bot}/{endpoint}")

    result = fetch_json(url)

    if "error" in result:
        print(f"    {RED}✗ ERROR: {result['error']}{RESET}")
        return False

    if not result.get("success", False):
        print(f"    {YELLOW}⚠ success=false{RESET}")
        return False

    data = result.get("data", {})

    # Check equity curve data
    equity_curve = data.get("equity_curve", [])
    if not equity_curve:
        print(f"    {YELLOW}⚠ No equity curve data{RESET}")
        return True  # Not necessarily a bug

    print(f"    {GREEN}✓ Equity curve: {len(equity_curve)} points{RESET}")

    # Check today's entry (last point) for daily_pnl
    today = datetime.now(ZoneInfo("America/Chicago")).strftime('%Y-%m-%d')
    today_points = [p for p in equity_curve if p.get("date") == today]

    if today_points:
        last = today_points[-1]
        daily_pnl = last.get("daily_pnl", 0)
        unrealized = last.get("unrealized_pnl", 0)
        realized = last.get("realized_pnl", 0)

        print(f"    Today's point found:")
        print(f"      daily_pnl: ${daily_pnl:,.2f}")
        print(f"      unrealized_pnl: ${unrealized:,.2f}")

        # Check if daily_pnl was incorrectly set to just unrealized
        if daily_pnl == unrealized and daily_pnl != 0:
            print(f"      {YELLOW}⚠ daily_pnl equals unrealized - check if today_realized should be added{RESET}")
        else:
            print(f"      {GREEN}✓ daily_pnl looks correct{RESET}")

    return True


def test_positions(base_url: str, bot: str):
    """Test positions endpoint"""
    url = f"{base_url}/api/{bot}/positions"
    print(f"\n  Testing: /api/{bot}/positions")

    result = fetch_json(url)

    if "error" in result:
        print(f"    {RED}✗ ERROR: {result['error']}{RESET}")
        return False

    data = result.get("data", {})
    closed = data.get("closed_positions", [])
    open_pos = data.get("open_positions", [])

    print(f"    Open positions: {len(open_pos)}")
    print(f"    Closed positions: {len(closed)}")

    if len(closed) == 0:
        # Check if this is the bug we fixed
        print(f"    {YELLOW}⚠ No closed positions returned - verify they exist in DB{RESET}")

    return True


def run_tests(base_url: str):
    """Run all API endpoint tests"""
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}ALPHAGEX API ENDPOINT TESTS{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"Base URL: {base_url}")
    print(f"Timestamp: {datetime.now(ZoneInfo('America/Chicago')).isoformat()}")

    # Test health endpoint first
    print(f"\n{BLUE}--- Health Check ---{RESET}")
    health = test_endpoint(base_url, "/health")
    if health["status"] == "error":
        print(f"\n{RED}Cannot connect to API. Is the server running?{RESET}")
        return 1

    # Bots to test
    bots = ["fortress", "samson", "anchor", "solomon", "gideon"]

    print(f"\n{BLUE}--- Bot Equity Curves ---{RESET}")
    for bot in bots:
        test_equity_curve(base_url, bot, "equity-curve")

    print(f"\n{BLUE}--- Bot Positions ---{RESET}")
    for bot in bots:
        test_positions(base_url, bot)

    print(f"\n{BLUE}--- Unified Metrics ---{RESET}")
    for bot in ["FORTRESS", "SAMSON", "ANCHOR", "SOLOMON", "GIDEON"]:
        test_endpoint(base_url, f"/api/metrics/{bot}/equity-curve")

    print(f"\n{BLUE}--- Events/Combined ---{RESET}")
    test_endpoint(base_url, "/api/events/equity-curve")
    test_endpoint(base_url, "/api/events/equity-curve?bot=FORTRESS")

    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{GREEN}API TESTS COMPLETE{RESET}")
    print(f"{BLUE}{'='*60}{RESET}")

    return 0


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

    # Remove trailing slash
    base_url = base_url.rstrip("/")

    return run_tests(base_url)


if __name__ == "__main__":
    sys.exit(main())
